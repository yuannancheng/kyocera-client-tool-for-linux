"""PJL transport for Kyocera printers over TCP 9100 or a USB character device."""

from __future__ import annotations

import os
import socket
import time
from collections import Counter
from contextlib import contextmanager
from typing import Iterator, Protocol

UEL = b"\x1b%-12345X"

# Query order validated through read-only interoperability testing.
QUERY_SEQUENCE = (
    "@PJL INFO CONFIG",
    "@PJL INFO KCONFIG",
    "@PJL INFO KNETWORKSTATUS",
    "@PJL INQUIRE TIMEOUT",
    "@PJL INFO KUNITNAME",
    "@PJL INFO KINTRAYSTATUS",
    "@PJL INFO ID",
    "@PJL INFO STATUS",
    '@PJL KGETOBJ OBJ="1.42.5.1.1.16.1"',
    '@PJL KGETOBJ OBJ="2.5.1.1.10.1"',
    '@PJL KGETOBJ OBJ="1.43.5.1.1.34.1"',
    '@PJL KGETOBJ OBJ="1.43.5.1.1.35.1"',
    '@PJL KGETOBJ OBJ="2.10.2.1.4.1.1"',
    '@PJL KGETOBJ OBJ="1.43.10.1.1.8.1.1"',
    '@PJL KGETOBJ OBJ="1.43.10.1.1.14.1.1"',
    '@PJL KGETOBJ OBJ="1.46.10.1.1.5.3"',
)

# The USB path sends INFO ID first; parsing that response triggers the remaining
# 15 queries (including KINTRAYSTATUS).
USB_QUERY_SEQUENCE = ("@PJL INFO ID",) + tuple(
    command for command in QUERY_SEQUENCE if command != "@PJL INFO ID"
)


class PjlError(RuntimeError):
    pass


class Channel(Protocol):
    def send(self, data: bytes) -> None: ...

    def drain(self) -> None: ...

    def receive(
        self, timeout: float, idle: float, expected: tuple[str, ...] | list[str] = ()
    ) -> bytes: ...


class TcpChannel:
    def __init__(self, host: str, port: int = 9100, connect_timeout: float = 5.0):
        self.host = host
        self.port = port
        self.sock = socket.create_connection((host, port), timeout=connect_timeout)

    def send(self, data: bytes) -> None:
        self.sock.sendall(data)

    def drain(self) -> None:
        pass

    def receive(
        self, timeout: float, idle: float, expected: tuple[str, ...] | list[str] = ()
    ) -> bytes:
        chunks: list[bytes] = []
        deadline = time.monotonic() + timeout
        last_data = time.monotonic()
        while time.monotonic() < deadline:
            self.sock.settimeout(min(idle, max(0.05, deadline - time.monotonic())))
            try:
                chunk = self.sock.recv(65535)
            except socket.timeout:
                # A partial response that stops arriving is handed back so the
                # caller can retry only the missing queries.
                if chunks and time.monotonic() - last_data >= idle:
                    break
                continue
            if not chunk:
                break
            chunks.append(chunk)
            last_data = time.monotonic()
            if response_complete(b"".join(chunks), expected):
                break
            if UEL in chunk:
                break
        return b"".join(chunks)

    def close(self) -> None:
        self.sock.close()


class DeviceChannel:
    """PJL over a kernel usblp character device such as /dev/usb/lp0."""

    def __init__(self, path: str):
        self.path = path
        try:
            self.fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        except OSError as exc:
            raise PjlError(f"cannot open USB printer {path}: {exc}") from exc

    def send(self, data: bytes) -> None:
        import select

        view = memoryview(data)
        deadline = time.monotonic() + 5.0
        while view:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PjlError(f"timed out writing to USB printer {self.path}")
            try:
                _, ready, _ = select.select([], [self.fd], [], remaining)
            except InterruptedError:
                continue
            if not ready:
                raise PjlError(f"timed out writing to USB printer {self.path}")
            try:
                written = os.write(self.fd, view)
            except BlockingIOError:
                continue
            except InterruptedError:
                continue
            except OSError as exc:
                raise PjlError(
                    f"error writing to USB printer {self.path}: {exc}"
                ) from exc
            if written <= 0:
                raise PjlError(f"short write to USB printer {self.path}")
            view = view[written:]

    def drain(self, idle: float = 0.05, limit: int = 65536) -> None:
        """Discard stale bytes left by an earlier query or status report."""
        import select

        total = 0
        while total < limit:
            try:
                ready, _, _ = select.select([self.fd], [], [], idle)
            except InterruptedError:
                continue
            if not ready:
                break
            try:
                chunk = os.read(self.fd, 4096)
            except BlockingIOError:
                break
            except InterruptedError:
                continue
            except OSError:
                break
            if not chunk:
                break
            total += len(chunk)

    def receive(
        self, timeout: float, idle: float, expected: tuple[str, ...] | list[str] = ()
    ) -> bytes:
        import select

        chunks: list[bytes] = []
        deadline = time.monotonic() + timeout
        last_data = time.monotonic()
        while time.monotonic() < deadline:
            remaining = max(0.05, deadline - time.monotonic())
            try:
                ready, _, _ = select.select(
                    [self.fd], [], [], min(idle, remaining)
                )
            except InterruptedError:
                continue
            if not ready:
                if chunks and time.monotonic() - last_data >= idle:
                    break
                continue
            try:
                chunk = os.read(self.fd, 4096)
            except BlockingIOError:
                continue
            except InterruptedError:
                continue
            except OSError as exc:
                raise PjlError(
                    f"error reading from USB printer {self.path}: {exc}"
                ) from exc
            if not chunk:
                break
            chunks.append(chunk)
            last_data = time.monotonic()
            if response_complete(b"".join(chunks), expected):
                break
            if UEL in chunk:
                break
        return b"".join(chunks)

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1


@contextmanager
def open_channel(
    *,
    host: str | None = None,
    port: int = 9100,
    device: str | None = None,
) -> Iterator[Channel]:
    channel: Channel
    if device:
        channel = DeviceChannel(device)
    elif host:
        channel = TcpChannel(host, port)
    else:
        raise PjlError("either host or device is required")
    try:
        channel.drain()
        yield channel
    finally:
        channel.close()


def build_request(queries: tuple[str, ...] | list[str]) -> bytes:
    payload = bytearray(UEL + b"\r\n")
    for command in queries:
        if "\r" in command or "\n" in command:
            raise PjlError(f"query contains a line break: {command!r}")
        payload.extend(command.encode("ascii") + b"\r\n")
    payload.extend(UEL + b"\r\n")
    return bytes(payload)


def response_complete(response: bytes, expected: tuple[str, ...] | list[str]) -> bool:
    if not expected:
        return False
    text = response.decode("ascii", "replace")
    return all(text.count(command) >= count for command, count in Counter(expected).items())


def normalize_command(command: str) -> str:
    """Normalize an echoed PJL command for segment matching."""
    return " ".join(command.strip().lstrip("\x0c").split()).upper()


def split_segments(response: bytes) -> dict[str, bytes]:
    """Split a PJL response into segments keyed by normalized command.

    The printer echoes each command before its payload and separates responses
    with a form feed. Some devices prefix the following echo with ``\x0c``, so
    the form feed is stripped from the segment start.
    """
    text = response.decode("ascii", "replace")
    segments: dict[str, str] = {}
    current: str | None = None
    body: list[str] = []
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip("\x0c")
        if stripped.startswith("@PJL "):
            if current is not None:
                segments.setdefault(current, "".join(body).rstrip("\x0c"))
            current = normalize_command(stripped)
            body = [stripped]
        elif current is not None:
            body.append(line)
    if current is not None:
        segments.setdefault(current, "".join(body).rstrip("\x0c"))
    return {
        command: segment.encode("ascii", "replace")
        for command, segment in segments.items()
    }


def merge_segments(
    segments: dict[str, bytes], commands: tuple[str, ...] | list[str]
) -> bytes:
    """Rebuild one response in the original query order."""
    parts = []
    for command in commands:
        segment = segments.get(normalize_command(command))
        if segment is not None:
            parts.append(segment)
    if not parts:
        return b""
    return b"\x0c".join(parts) + b"\x0c"


def missing_commands(
    response: bytes, commands: tuple[str, ...] | list[str]
) -> list[str]:
    found = split_segments(response)
    return [
        command for command in commands if normalize_command(command) not in found
    ]


def query(
    channel: Channel,
    commands: tuple[str, ...] | list[str] = QUERY_SEQUENCE,
    *,
    timeout: float = 8.0,
    idle: float = 1.5,
    retries: int = 1,
) -> bytes:
    request = build_request(commands)
    for attempt in range(retries + 1):
        channel.drain()
        channel.send(request)
        response = channel.receive(timeout, idle, commands)
        if response:
            return response
        if attempt < retries:
            time.sleep(0.3)
    raise PjlError("printer returned no PJL response")


def query_merged(
    channel: Channel,
    commands: tuple[str, ...] | list[str] = QUERY_SEQUENCE,
    *,
    timeout: float = 8.0,
    idle: float = 1.5,
    retries: int = 2,
) -> bytes:
    """Query the printer and retry only the segments that were not answered.

    The MA2000w occasionally drops the tail of a long query batch while it is
    waking up. Resending the complete batch wastes the earlier answers and can
    lose a different subset again, so each retry contains only the missing
    commands and the answers are merged in the original order.
    """
    commands = tuple(commands)
    remaining = list(commands)
    collected: dict[str, bytes] = {}
    last_response = b""
    for attempt in range(retries + 1):
        if not remaining:
            break
        channel.drain()
        channel.send(build_request(remaining))
        response = channel.receive(timeout, idle, remaining)
        last_response = response
        found = split_segments(response)
        for command in list(remaining):
            segment = found.get(normalize_command(command))
            if segment is not None:
                collected[normalize_command(command)] = segment
                remaining.remove(command)
        if response and not found:
            # Unrecognized bytes cannot be mapped to a query; retrying the
            # remaining batch is more useful than returning a partial answer.
            if attempt < retries:
                time.sleep(0.2)
            continue
        if remaining and attempt < retries:
            time.sleep(0.2)
    if not collected:
        # Some devices may answer without echoing the command. Keep the raw
        # bytes so the parser can still try, matching the old behavior.
        if last_response:
            return last_response
        raise PjlError("printer returned no PJL response")
    return merge_segments(collected, commands)
