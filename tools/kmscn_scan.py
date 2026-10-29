#!/usr/bin/env python3
"""Run one KM-WSDL scan using the device's reported default configuration."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kyocera_monitor import kmscn, kmscn_raw


def decode_image_data(value: str | None) -> bytes:
    if value is None:
        return b""
    compact = "".join(value.split())
    try:
        return base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError):
        return value.encode("utf-8")


def response_payload(response: kmscn.ScanResponse) -> dict[str, object]:
    payload = asdict(response)
    payload.pop("body", None)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target")
    parser.add_argument("--https", action="store_true")
    parser.add_argument("--port", type=int)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("scan-output.raw"))
    parser.add_argument(
        "--decoded-output",
        type=Path,
        help="BMP output path (default: output path with .bmp suffix)",
    )
    parser.add_argument(
        "--no-decode",
        action="store_true",
        help="keep only the vendor RAW stream",
    )
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--max-polls", type=int, default=60)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument(
        "--format",
        choices=("RAW", "JPEG", "TIFF"),
        help="override the device default image_file_format",
    )
    parser.add_argument(
        "--operation-id",
        help="reuse an already-open operation instead of opening a new session",
    )
    parser.add_argument(
        "--retrieve-only",
        action="store_true",
        help="retrieve an already-started operation; requires --operation-id",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--raw", action="store_true")
    args = parser.parse_args(argv)
    if args.max_pages < 1:
        parser.error("--max-pages must be positive")
    if args.max_polls < 1:
        parser.error("--max-polls must be positive")
    if args.retrieve_only and args.operation_id is None:
        parser.error("--retrieve-only requires --operation-id")

    try:
        _, endpoint = kmscn.build_endpoint(args.target, args.https, args.port)
        preflight = kmscn.preflight(
            endpoint,
            timeout=args.timeout,
            insecure=args.insecure,
            include_raw=args.raw,
        )
        if not preflight.ok:
            payload = {"ok": False, "stage": "preflight", "preflight": asdict(preflight)}
            print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload)
            return 1

        defaults = kmscn.probe_default_configuration(
            endpoint,
            timeout=args.timeout,
            insecure=args.insecure,
            include_raw=args.raw,
        )
        if not defaults.ok or defaults.configuration is None:
            payload = {"ok": False, "stage": "default_configuration"}
            print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload)
            return 1
        configuration = defaults.configuration
        if args.format is not None:
            configuration = kmscn.replace_configuration_value(
                configuration,
                "image_file_format",
                args.format,
            )

        if args.operation_id is not None:
            operation_id = args.operation_id
        else:
            opened = kmscn.open_session(
                endpoint,
                timeout=args.timeout,
                insecure=args.insecure,
                include_raw=args.raw,
            )
            if not opened.ok or opened.operation_id is None:
                payload = {
                    "ok": False,
                    "stage": "open_session",
                    "response": response_payload(opened),
                }
                print(
                    json.dumps(payload, ensure_ascii=False, indent=2)
                    if args.json
                    else payload
                )
                return 1
            operation_id = opened.operation_id
        output_files: list[dict[str, object]] = []
        decoded_outputs: list[dict[str, object]] = []
        started = None
        completed = False
        try:
            if not args.retrieve_only:
                started = kmscn.start_scan(
                    endpoint,
                    operation_id,
                    configuration,
                    timeout=args.timeout,
                    insecure=args.insecure,
                    include_raw=args.raw,
                )
                if not started.ok:
                    payload = {
                        "ok": False,
                        "stage": "start_scan",
                        "response": response_payload(started),
                    }
                    print(
                        json.dumps(payload, ensure_ascii=False, indent=2)
                        if args.json
                        else payload
                    )
                    return 1

            pages_saved = 0
            for poll in range(1, args.max_polls + 1):
                retrieved = kmscn.retrieve_image(
                    endpoint,
                    operation_id,
                    timeout=args.timeout,
                    insecure=args.insecure,
                    include_raw=args.raw,
                )
                if not retrieved.ok:
                    payload = {
                        "ok": False,
                        "stage": "retrieve_image",
                        "page": pages_saved + 1,
                        "poll": poll,
                        "response": response_payload(retrieved),
                    }
                    print(
                        json.dumps(payload, ensure_ascii=False, indent=2)
                        if args.json
                        else payload
                    )
                    return 1
                if retrieved.result == "ALL_GET_COMPLETE":
                    completed = True
                    break
                if retrieved.result == "IMAGE_CREATING_NOW":
                    time.sleep(args.poll_interval)
                    continue
                data = decode_image_data(retrieved.image_data)
                if not data and retrieved.body is not None:
                    data = retrieved.body
                if not data:
                    payload = {
                        "ok": False,
                        "stage": "retrieve_image",
                        "page": pages_saved + 1,
                        "poll": poll,
                        "error": "image did not become available",
                    }
                    print(
                        json.dumps(payload, ensure_ascii=False, indent=2)
                        if args.json
                        else payload
                    )
                    return 1
                if pages_saved >= args.max_pages:
                    time.sleep(args.poll_interval)
                    continue
                pages_saved += 1
                output = args.output
                if args.max_pages > 1:
                    output = output.with_name(
                        f"{output.stem}-{pages_saved}{output.suffix}"
                    )
                output.write_bytes(data)
                output_files.append(
                    {
                        "path": str(output),
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
                if not args.no_decode:
                    try:
                        decoded = kmscn_raw.decode_raw(data)
                        decoded_path = (
                            args.decoded_output
                            if args.decoded_output is not None
                            else output.with_suffix(".bmp")
                        )
                        if args.max_pages > 1 and args.decoded_output is not None:
                            decoded_path = decoded_path.with_name(
                                f"{decoded_path.stem}-{pages_saved}"
                                f"{decoded_path.suffix}"
                            )
                        bmp = kmscn_raw.encode_bmp(decoded)
                        decoded_path.write_bytes(bmp)
                        decoded_outputs.append(
                            {
                                "path": str(decoded_path),
                                "width": decoded.width,
                                "height": decoded.height,
                                "bytes": len(bmp),
                                "sha256": hashlib.sha256(bmp).hexdigest(),
                            }
                        )
                    except ValueError as error:
                        payload = {
                            "ok": False,
                            "stage": "decode_raw",
                            "page": pages_saved,
                            "error": str(error),
                            "raw_output": str(output),
                        }
                        print(
                            json.dumps(payload, ensure_ascii=False, indent=2)
                            if args.json
                            else payload
                        )
                        return 1
                time.sleep(args.poll_interval)
            else:
                payload = {
                    "ok": False,
                    "stage": "retrieve_image",
                    "error": "scan did not report ALL_GET_COMPLETE",
                    "polls": args.max_polls,
                    "outputs": output_files,
                }
                print(
                    json.dumps(payload, ensure_ascii=False, indent=2)
                    if args.json
                    else payload
                )
                return 1
        finally:
            closed = kmscn.close_session(
                endpoint,
                operation_id,
                timeout=args.timeout,
                insecure=args.insecure,
                include_raw=args.raw,
            )

        payload = {
            "ok": completed,
            "endpoint": endpoint,
            "operation_id": operation_id,
            "outputs": output_files,
            "decoded_outputs": decoded_outputs,
            "completed": completed,
            "close_result": closed.result,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if completed else 1
    except (OSError, ValueError) as error:
        print(f"KM-WSDL scan failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
