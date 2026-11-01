"""Persistent user preferences for scan presets and local output folders."""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Callable

from .scan import ScanOptions

SETTINGS_VERSION = 1
MAX_PRESETS = 30
_PRESET_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_PRESET_FIELDS = {
    "color",
    "resolution",
    "original_image",
    "max_pages",
    "output_format",
}


class SettingsError(ValueError):
    """Raised when local preferences are invalid or cannot be loaded."""


def default_settings_path() -> Path:
    root = os.environ.get("XDG_CONFIG_HOME")
    base = Path(root).expanduser() if root else Path.home() / ".config"
    return base / "kyocera-monitor" / "settings.json"


def default_scan_directory() -> str:
    return str(Path.home() / "Pictures" / "Kyocera Scans")


def default_settings() -> dict[str, object]:
    return {
        "version": SETTINGS_VERSION,
        "scan_directory": default_scan_directory(),
        "presets": [],
    }


def _required_text(
    payload: dict[str, object], name: str, *, maximum: int
) -> str:
    value = payload.get(name)
    if not isinstance(value, str):
        raise SettingsError(f"{name} must be a string")
    value = value.strip()
    if not value or len(value) > maximum or "\x00" in value:
        raise SettingsError(f"{name} must contain 1-{maximum} characters")
    return value


def _optional_text(
    payload: dict[str, object], name: str
) -> str | None:
    value = payload.get(name)
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise SettingsError(f"{name} must be a string or null")
    return value


def normalize_scan_directory(value: object) -> str:
    if not isinstance(value, str):
        raise SettingsError("scan_directory must be a string")
    text = value.strip()
    if not text or len(text) > 4096 or "\x00" in text:
        raise SettingsError("scan_directory must be a non-empty path")
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise SettingsError("scan_directory must be an absolute path")
    return str(path)


def normalize_preset(value: object, index: int) -> dict[str, object]:
    if not isinstance(value, dict):
        raise SettingsError(f"presets[{index}] must be an object")
    unknown = set(value) - (_PRESET_FIELDS | {"id", "name"})
    if unknown:
        raise SettingsError(
            f"presets[{index}] has unsupported fields: "
            + ", ".join(sorted(unknown))
        )
    preset_id = _required_text(value, "id", maximum=64)
    if not _PRESET_ID_RE.fullmatch(preset_id):
        raise SettingsError(
            f"presets[{index}].id must use lowercase letters, digits and '-'"
        )
    name = _required_text(value, "name", maximum=80)
    output_format = value.get("output_format", "png")
    if not isinstance(output_format, str):
        raise SettingsError(
            f"presets[{index}].output_format must be a string"
        )
    output_format = output_format.lower()
    max_pages = value.get("max_pages", 1)
    if isinstance(max_pages, bool) or not isinstance(max_pages, int):
        raise SettingsError(f"presets[{index}].max_pages must be an integer")
    try:
        options = ScanOptions(
            color=_optional_text(value, "color"),
            resolution=_optional_text(value, "resolution"),
            original_image=_optional_text(value, "original_image"),
            output_format=output_format,
            max_pages=max_pages,
        )
    except ValueError as exc:
        raise SettingsError(f"presets[{index}]: {exc}") from exc
    return {
        "id": preset_id,
        "name": name,
        "color": options.color,
        "resolution": options.resolution,
        "original_image": options.original_image,
        "max_pages": options.max_pages,
        "output_format": options.output_format,
    }


def normalize_settings(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise SettingsError("settings must be a JSON object")
    unknown = set(value) - {"version", "scan_directory", "presets"}
    if unknown:
        raise SettingsError(
            "settings has unsupported fields: " + ", ".join(sorted(unknown))
        )
    version = value.get("version", SETTINGS_VERSION)
    if version != SETTINGS_VERSION:
        raise SettingsError(f"unsupported settings version: {version!r}")
    presets = value.get("presets", [])
    if not isinstance(presets, list):
        raise SettingsError("presets must be an array")
    if len(presets) > MAX_PRESETS:
        raise SettingsError(f"at most {MAX_PRESETS} presets are supported")
    normalized_presets = [
        normalize_preset(preset, index)
        for index, preset in enumerate(presets)
    ]
    ids = [preset["id"] for preset in normalized_presets]
    if len(ids) != len(set(ids)):
        raise SettingsError("preset ids must be unique")
    return {
        "version": SETTINGS_VERSION,
        "scan_directory": normalize_scan_directory(
            value.get("scan_directory", default_scan_directory())
        ),
        "presets": normalized_presets,
    }


class SettingsStore:
    """Thread-safe, integrity-checked JSON settings owned by one user."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        defaults: Callable[[], dict[str, object]] = default_settings,
    ):
        self.path = path or default_settings_path()
        self._defaults = defaults
        self._lock = threading.Lock()

    def load(self) -> dict[str, object]:
        with self._lock:
            if not self.path.exists():
                return normalize_settings(self._defaults())
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise SettingsError(
                    f"cannot read settings {self.path}: {type(exc).__name__}: {exc}"
                ) from exc
            return normalize_settings(payload)

    def save(self, value: object) -> dict[str, object]:
        settings = normalize_settings(value)
        encoded = (
            json.dumps(settings, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")
        with self._lock:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{self.path.name}.",
                dir=self.path.parent,
            )
            try:
                os.fchmod(descriptor, 0o600)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary_name, self.path)
                os.chmod(self.path, 0o600)
            except Exception:
                try:
                    os.unlink(temporary_name)
                except FileNotFoundError:
                    pass
                raise
        return settings


def preset_payload(settings: dict[str, object], preset_id: object) -> dict[str, object] | None:
    if preset_id in (None, ""):
        return None
    if not isinstance(preset_id, str):
        raise SettingsError("preset_id must be a string or null")
    for preset in settings["presets"]:
        if preset["id"] == preset_id:
            return preset
    raise SettingsError(f"unknown preset: {preset_id}")


def merge_scan_payload(
    payload: dict[str, object],
    preset: dict[str, object] | None,
) -> dict[str, object]:
    merged = dict(payload)
    if preset is not None:
        for name in _PRESET_FIELDS:
            if merged.get(name) in (None, ""):
                merged[name] = preset[name]
    merged.pop("preset_id", None)
    merged.pop("save_to_folder", None)
    return merged
