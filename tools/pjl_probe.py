#!/usr/bin/env python3
"""Send PJL queries to a Kyocera printer and print the raw response."""

from __future__ import annotations

import argparse
import socket
import sys
import time

UEL = b"\x1b%-12345X"


def build_request(queries: list[str], keep_connection: bool) -> bytes:
    payload = bytearray(UEL + b"\r\n")
    for query in queries:
        payload.extend(query.encode("ascii") + b"\r\n")
    if not keep_connection:
        payload.extend(UEL + b"\r\n")
    return bytes(payload)


def receive(sock: socket.socket, timeout: float, idle: float) -> bytes:
    chunks: list[bytes] = []
    deadline = time.monotonic() + timeout
    sock.settimeout(idle)
    while time.monotonic() < deadline:
        try:
            chunk = sock.recv(65535)
        except socket.timeout:
            break
        if not chunk:
            break
        chunks.append(chunk)
        if UEL in chunk:
            break
    return b"".join(chunks)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host")
    parser.add_argument("queries", nargs="+")
    parser.add_argument("--port", type=int, default=9100)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--idle", type=float, default=1.5)
    parser.add_argument("--keep-connection", action="store_true")
    parser.add_argument("--hex", action="store_true")
    args = parser.parse_args()

    request = build_request(args.queries, args.keep_connection)
    try:
        with socket.create_connection((args.host, args.port), timeout=args.timeout) as sock:
            sock.sendall(request)
            response = receive(sock, args.timeout, args.idle)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"request: {len(request)} bytes, response: {len(response)} bytes")
    if args.hex:
        print(response.hex())
    text = response.replace(UEL, b"<UEL>").decode("ascii", "backslashreplace")
    print(text.replace("\r", "\\r").replace("\n", "\\n"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
