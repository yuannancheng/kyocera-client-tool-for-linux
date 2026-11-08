"""Official Client Tool media, paper-size, and paper-weight labels.

The value tables and labels are reproduced from the hash-pinned Client Tool
1.4.11.2 resources:

* ``KMUTLCFG.exe`` SHA-256
  ``63e202a050fe44611377deb4c5d01246da45fd51cda22f308ff990867730c9ea``
* table ``0x00497458``: paper-size value -> RT_STRING id
* table ``0x00497c68``: media-type value -> RT_STRING id
* ``LANG/zh-Hans/KMUTLCFGRes.dll`` SHA-256
  ``ae3b8ee53860f235fa8f180c23b3aca382af6f8e0f45fe79131b5a5210abcd96``

Only the names needed by this independent Linux implementation are stored
here.  The official binaries are not loaded or shipped at runtime.
"""

from __future__ import annotations


# The official Client Tool subtracts 10 from the stored paper-weight value
# before selecting its weight combo box.
PAPER_WEIGHT_NAMES: dict[int, str] = {
    10: "轻",
    11: "普通 1",
    12: "普通 2",
    13: "普通 3",
    14: "重 1",
    15: "重 2",
    16: "重 3",
}


# The normal media-type table at 0x00497c68.
MEDIA_TYPE_NAMES: dict[int, str] = {
    1: "普通纸",
    2: "预印纸",
    3: "标签纸",
    4: "铜版纸",
    5: "再生纸",
    6: "牛皮纸",
    7: "粗糙纸",
    8: "公函信笺",
    9: "彩色纸",
    10: "预打孔纸",
    11: "信封纸",
    12: "卡片纸",
    13: "厚纸",
    14: "高质量纸",
    15: "自定义 1",
    16: "自定义 2",
    17: "自定义 3",
    18: "自定义 4",
    19: "自定义 5",
    20: "自定义 6",
    21: "自定义 7",
    22: "自定义 8",
}

_MEDIA_TYPE_ALIASES: dict[str, str] = {
    "plain": "普通纸",
    "preprinted": "预印纸",
    "labels": "标签纸",
    "bond": "铜版纸",
    "recycled": "再生纸",
    "vellum": "牛皮纸",
    "rough": "粗糙纸",
    "letterhead": "公函信笺",
    "color": "彩色纸",
    "prepunched": "预打孔纸",
    "envelope": "信封纸",
    "cardstock": "卡片纸",
    "thick": "厚纸",
    "high quality": "高质量纸",
    "fine": "精细纸",
}


# The normal paper-size table at 0x00497458.  This device family has no
# value 19 and uses 20 as the custom-size sentinel.
PAPER_SIZE_NAMES: dict[int, str] = {
    0: "信封 Monarch",
    1: "信封 #10",
    2: "信封 DL",
    3: "信封 C5",
    4: "信封 #9",
    5: "信封 #6",
    6: "Executive",
    7: "Letter",
    8: "Legal",
    9: "A4",
    10: "A5",
    11: "A6",
    12: "B5 (JIS)",
    13: "B5 (ISO)",
    14: "216 × 340 mm",
    15: "Oficio II",
    16: "16 开",
    17: "Statement",
    18: "Folio",
    20: "自定义尺寸",
}


MEDIA_WEIGHT_OIDS = frozenset(
    f"43.21.1.1.3.1.{media_type}" for media_type in MEDIA_TYPE_NAMES
)


def media_type_name(value: int) -> str | None:
    """Return the official media-type label for a device value."""

    return MEDIA_TYPE_NAMES.get(value)


def paper_size_name(value: int) -> str | None:
    """Return the official paper-size label for a device value."""

    return PAPER_SIZE_NAMES.get(value)


def paper_weight_name(value: int) -> str | None:
    """Return the official paper-weight label for a device value."""

    return PAPER_WEIGHT_NAMES.get(value)


def media_weight_setting_name(oid: str) -> str | None:
    """Return a friendly title for one of the 22 media-weight objects."""

    prefix = "43.21.1.1.3.1."
    if not oid.startswith(prefix):
        return None
    suffix = oid[len(prefix) :]
    if not suffix.isdigit():
        return None
    media = media_type_name(int(suffix))
    if not media:
        return None
    if media.startswith("自定义"):
        return f"{media} 纸张重量"
    return f"{media}重量"


def display_media_value(oid: str, value: object) -> object:
    """Render one official media object without exposing the raw enum."""

    if not isinstance(value, int) or isinstance(value, bool):
        return value
    if oid == "43.8.1.1.11.1.1":
        return paper_size_name(value) or "未识别的纸张尺寸"
    if oid == "43.8.1.1.4.1.1":
        return media_type_name(value) or "未识别的介质类型"
    if oid in MEDIA_WEIGHT_OIDS:
        return paper_weight_name(value) or "未识别的纸张重量"
    return value


def display_tray_paper(size: object, media: object) -> str | None:
    """Combine tray size and media into one short, user-facing label."""

    parts: list[str] = []
    if size not in (None, ""):
        parts.append(str(size))
    if media not in (None, "", "UNKNOWN", "unknown"):
        text = str(media)
        try:
            media_name = MEDIA_TYPE_NAMES.get(int(text, 10))
        except ValueError:
            media_name = _MEDIA_TYPE_ALIASES.get(
                " ".join(text.split()).casefold()
            )
        parts.append(media_name or text)
    return " · ".join(dict.fromkeys(parts)) or None


__all__ = [
    "MEDIA_TYPE_NAMES",
    "MEDIA_WEIGHT_OIDS",
    "PAPER_SIZE_NAMES",
    "PAPER_WEIGHT_NAMES",
    "display_media_value",
    "display_tray_paper",
    "media_type_name",
    "media_weight_setting_name",
    "paper_size_name",
    "paper_weight_name",
]
