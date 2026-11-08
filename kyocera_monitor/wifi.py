"""KYOCERA Wi-Fi Setup Tool protocol over PJL.

The official Wi-Fi Setup Tool communicates through the Windows language
monitor, but its application-level operations are PJL ``KGETOBJ`` and
``KSETOBJ`` requests.  This module sends the same object identifiers and SET
order directly over TCP 9100 or the Linux USB printer interface.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from contextlib import AbstractContextManager
from typing import Callable

from .pjl import Channel, build_request


class WifiError(RuntimeError):
    pass


SECURITY_MODES = {
    0: "Open (no encryption)",
    1: "Open (WEP)",
    2: "WPA/WPA2 PSK (AES)",
    3: "WPA/WPA2 PSK (Auto)",
    4: "WPA2 PSK (AES)",
}

WIFI_CONNECTION_STATE = "40.42.1.1.1.1"
WIFI_ENABLE_STATE = "40.42.1.1.3.1"
WIFI_SSID = "40.42.1.1.4.1"
WIFI_SECURITY = "40.42.1.1.5.1"
WIFI_CHANNEL = "40.42.1.1.6.1"
WIFI_RSSI = "40.42.1.1.7.1"

AP_TOTAL = "40.39.1.1.10.1.1"
AP_SSID = "40.39.1.1.1.1"
AP_SECURITY = "40.39.1.1.2.1"
AP_BSSID = "40.39.1.1.3.1"
AP_RSSI = "40.39.1.1.6.1"

SET_AP_SSID = "40.40.1.1.1.1"
SET_AP_SECURITY = "40.40.1.1.2.1"
SET_AP_BSSID = "40.40.1.1.3.1"
SET_AP_WEP_INDEX = "40.40.1.1.7.1"
SET_AP_WEP_KEY = "40.40.1.1.8.1"
SET_AP_PSK = "40.40.1.1.9.1"
SET_AP_RESULT = "40.40.1.1.10.1"


@dataclass(frozen=True)
class WifiObject:
    status: int
    type_code: int
    value: str


@dataclass(frozen=True)
class AccessPoint:
    index: int
    ssid: str
    security: int
    security_name: str
    bssid: str
    rssi: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "ssid": self.ssid,
            "security": self.security,
            "security_name": self.security_name,
            "bssid": self.bssid,
            "rssi": self.rssi,
        }


class WifiWorkbench:
    """Open a fresh PJL channel for each dashboard Wi-Fi operation."""

    def __init__(
        self,
        channel_factory: Callable[[str], AbstractContextManager[Channel]],
        *,
        timeout: float = 8.0,
        idle: float = 1.5,
        scan_timeout: float = 20.0,
        connect_timeout: float = 25.0,
    ):
        self.channel_factory = channel_factory
        self.timeout = timeout
        self.idle = idle
        self.scan_timeout = scan_timeout
        self.connect_timeout = connect_timeout

    def status(self, target: str) -> dict[str, object]:
        with self.channel_factory(target) as channel:
            return read_wifi_status(
                channel,
                timeout=self.timeout,
                idle=self.idle,
            )

    def scan(self, target: str) -> list[dict[str, object]]:
        with self.channel_factory(target) as channel:
            return [
                point.to_dict()
                for point in scan_access_points(
                    channel,
                    timeout=self.timeout,
                    idle=self.idle,
                    scan_timeout=self.scan_timeout,
                )
            ]

    def connect(
        self,
        target: str,
        *,
        ssid: str,
        security: int,
        password: str | None,
        bssid: str = "",
        wep_index: int = 0,
    ) -> dict[str, object]:
        with self.channel_factory(target) as channel:
            return connect_access_point(
                channel,
                ssid=ssid,
                security=security,
                password=password,
                bssid=bssid,
                wep_index=wep_index,
                timeout=self.timeout,
                idle=self.idle,
                connect_timeout=self.connect_timeout,
            )


def _pjl_oid(oid: str) -> str:
    if oid.startswith("1.3.6.1.4.1.1347."):
        return "#" + oid
    return "1." + oid


def _field(raw: bytes, name: str) -> str | None:
    match = re.search(
        rb"(?:^|\r?\n)" + re.escape(name.encode("ascii")) + rb"=(.*?)\r?(?:\n|$)",
        raw,
        re.DOTALL,
    )
    if match is None:
        return None
    value = match.group(1).decode("utf-8", "replace")
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    return value


def _transaction(
    channel: Channel,
    command: str,
    *,
    timeout: float,
    idle: float,
) -> bytes:
    channel.drain()
    channel.send(build_request((command,)))
    return channel.receive(timeout, idle, (command,))


def get_object(
    channel: Channel,
    oid: str,
    *,
    timeout: float = 5.0,
    idle: float = 0.5,
) -> WifiObject:
    command = f'@PJL KGETOBJ OBJ="{_pjl_oid(oid)}"'
    raw = _transaction(channel, command, timeout=timeout, idle=idle)
    if not raw:
        raise WifiError(f"no response for Wi-Fi object {oid}")
    status_text = _field(raw, "STATUS")
    type_text = _field(raw, "TYPE")
    value_text = _field(raw, "VALUE")
    if status_text is None or type_text is None or value_text is None:
        raise WifiError(f"malformed PJL response for Wi-Fi object {oid}")
    try:
        return WifiObject(int(status_text), int(type_text), value_text)
    except ValueError as exc:
        raise WifiError(f"malformed numeric field for Wi-Fi object {oid}") from exc


def set_object(
    channel: Channel,
    oid: str,
    value: str,
    *,
    quote: bool,
    timeout: float = 5.0,
    idle: float = 0.5,
) -> int:
    encoded = f'"{value}"' if quote else value
    command = f'@PJL KSETOBJ OBJ="{_pjl_oid(oid)}" VALUE ={encoded}'
    raw = _transaction(channel, command, timeout=timeout, idle=idle)
    if not raw:
        raise WifiError(f"no response setting Wi-Fi object {oid}")
    status_text = _field(raw, "STATUS")
    if status_text is None:
        raise WifiError(f"malformed SET response for Wi-Fi object {oid}")
    try:
        return int(status_text)
    except ValueError as exc:
        raise WifiError(f"invalid SET status for Wi-Fi object {oid}") from exc


def _required_integer(
    channel: Channel,
    oid: str,
    *,
    timeout: float,
    idle: float,
) -> int:
    obj = get_object(channel, oid, timeout=timeout, idle=idle)
    if obj.status != 0:
        raise WifiError(f"Wi-Fi object {oid} returned STATUS={obj.status}")
    try:
        return int(obj.value.strip())
    except ValueError as exc:
        raise WifiError(f"Wi-Fi object {oid} is not an integer") from exc


def _required_text(
    channel: Channel,
    oid: str,
    *,
    timeout: float,
    idle: float,
) -> str:
    obj = get_object(channel, oid, timeout=timeout, idle=idle)
    if obj.status != 0:
        raise WifiError(f"Wi-Fi object {oid} returned STATUS={obj.status}")
    return obj.value


def read_wifi_status(
    channel: Channel,
    *,
    timeout: float = 5.0,
    idle: float = 0.5,
) -> dict[str, object]:
    connection = _required_integer(
        channel, WIFI_CONNECTION_STATE, timeout=timeout, idle=idle
    )
    enabled = _required_integer(
        channel, WIFI_ENABLE_STATE, timeout=timeout, idle=idle
    )
    ssid = _decode_hex_text(
        _required_text(channel, WIFI_SSID, timeout=timeout, idle=idle)
    )
    security = _required_integer(
        channel, WIFI_SECURITY, timeout=timeout, idle=idle
    )
    channel_number = _required_integer(
        channel, WIFI_CHANNEL, timeout=timeout, idle=idle
    )
    rssi = _required_integer(channel, WIFI_RSSI, timeout=timeout, idle=idle)
    return {
        "connection_state": connection,
        "connected": connection == 3,
        "enable_state": enabled,
        "ssid": ssid,
        "security": security,
        "security_name": SECURITY_MODES.get(security, f"Unknown ({security})"),
        "channel": channel_number,
        "rssi": rssi,
    }


def _decode_hex_text(value: str) -> str:
    compact = value.replace("-", "").replace(":", "").strip()
    try:
        raw = bytes.fromhex(compact)
    except ValueError:
        return value
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin1", "replace")


def _encode_hex_text(value: str) -> str:
    return value.encode("utf-8").hex().upper()


def scan_access_points(
    channel: Channel,
    *,
    timeout: float = 5.0,
    idle: float = 0.5,
    scan_timeout: float = 20.0,
    poll_interval: float = 1.0,
) -> list[AccessPoint]:
    status = set_object(
        channel,
        AP_TOTAL,
        "1",
        quote=False,
        timeout=timeout,
        idle=idle,
    )
    if status != 0:
        raise WifiError(f"Wi-Fi access-point scan returned STATUS={status}")

    deadline = time.monotonic() + scan_timeout
    total = -1
    while True:
        total = _required_integer(
            channel, AP_TOTAL, timeout=timeout, idle=idle
        )
        if total >= 0:
            break
        if time.monotonic() >= deadline:
            raise WifiError("timed out waiting for Wi-Fi access-point scan")
        time.sleep(poll_interval)

    access_points: list[AccessPoint] = []
    for index in range(1, total + 1):
        ssid = _decode_hex_text(
            _required_text(
                channel,
                f"{AP_SSID}.{index}",
                timeout=timeout,
                idle=idle,
            )
        )
        security = _required_integer(
            channel,
            f"{AP_SECURITY}.{index}",
            timeout=timeout,
            idle=idle,
        )
        bssid = _required_text(
            channel,
            f"{AP_BSSID}.{index}",
            timeout=timeout,
            idle=idle,
        )
        rssi_value = _required_text(
            channel,
            f"{AP_RSSI}.{index}",
            timeout=timeout,
            idle=idle,
        )
        try:
            rssi: int | None = int(rssi_value)
        except ValueError:
            rssi = None
        access_points.append(
            AccessPoint(
                index=index,
                ssid=ssid,
                security=security,
                security_name=SECURITY_MODES.get(
                    security, f"Unknown ({security})"
                ),
                bssid=bssid,
                rssi=rssi,
            )
        )
    return access_points


def connect_access_point(
    channel: Channel,
    *,
    ssid: str,
    security: int,
    password: str | None = None,
    bssid: str = "",
    wep_index: int = 0,
    timeout: float = 5.0,
    idle: float = 0.5,
    connect_timeout: float = 25.0,
    poll_interval: float = 1.0,
    on_progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    if not ssid:
        raise WifiError("SSID must not be empty")
    if security not in SECURITY_MODES:
        raise WifiError(f"unsupported Wi-Fi security mode: {security}")
    if security in (2, 3, 4) and not password:
        raise WifiError("WPA/WPA2 PSK requires a password")
    if security == 1 and not password:
        raise WifiError("WEP requires a key")

    def progress(message: str) -> None:
        if on_progress is not None:
            on_progress(message)

    writes: list[tuple[str, str, bool]] = [
        (SET_AP_SSID, _encode_hex_text(ssid), True),
        (SET_AP_SECURITY, str(security), False),
        (SET_AP_BSSID, bssid, True),
        (SET_AP_WEP_INDEX, str(wep_index), False),
        (
            SET_AP_WEP_KEY,
            _encode_hex_text(password or "") if security == 1 else "",
            True,
        ),
        (
            SET_AP_PSK,
            _encode_hex_text(password or "") if security in (2, 3, 4) else "",
            True,
        ),
    ]
    for oid, value, quote in writes:
        progress(f"writing {oid}")
        status = set_object(
            channel,
            oid,
            value,
            quote=quote,
            timeout=timeout,
            idle=idle,
        )
        if status != 0:
            raise WifiError(f"Wi-Fi SET {oid} returned STATUS={status}")

    deadline = time.monotonic() + connect_timeout
    while True:
        result = get_object(
            channel,
            SET_AP_RESULT,
            timeout=timeout,
            idle=idle,
        )
        state = _required_integer(
            channel,
            WIFI_CONNECTION_STATE,
            timeout=timeout,
            idle=idle,
        )
        if result.status == 0 and result.value.strip() == "0" and state == 3:
            return {
                "connected": True,
                "ssid": ssid,
                "security": security,
                "security_name": SECURITY_MODES[security],
                "connection_state": state,
                "set_result": result.value,
            }
        if time.monotonic() >= deadline:
            raise WifiError(
                "timed out waiting for Wi-Fi association "
                f"(SET result status={result.status}, value={result.value!r}, "
                f"connection_state={state})"
            )
        time.sleep(poll_interval)
