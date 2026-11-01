#!/usr/bin/env python3
"""Compatibility CLI for the integrated :mod:`kyocera_monitor.scan` service."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kyocera_monitor import kmscn
from kyocera_monitor.scan import (
    LOCAL_OUTPUT_FORMATS,
    ScanError,
    ScanOptions,
    scan_device,
    write_outputs,
)


def _local_format(
    decoded_output: Path | None,
    no_decode: bool,
    explicit: str | None,
) -> str:
    if explicit is not None:
        return explicit
    if no_decode:
        return "raw"
    if decoded_output is None:
        return "bmp"
    suffix = decoded_output.suffix.lower()
    if suffix in {".png", ".pdf", ".jpg", ".jpeg", ".tif", ".tiff", ".xps", ".bmp"}:
        return {
            ".jpg": "jpeg",
            ".jpeg": "jpeg",
            ".tif": "tiff",
            ".tiff": "tiff",
        }.get(suffix, suffix[1:])
    return "bmp"


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
        help=(
            "PNG, PDF, or BMP output (default: --output with .bmp suffix); "
            "this wrapper emits the selected local format instead of both RAW and BMP"
        ),
    )
    parser.add_argument("--no-decode", action="store_true")
    parser.add_argument(
        "--local-format",
        choices=LOCAL_OUTPUT_FORMATS,
        help="user-facing output format; overrides the --decoded-output suffix",
    )
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--max-polls", type=int, default=60)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument(
        "--max-response-bytes", type=int, default=64 * 1024 * 1024
    )
    parser.add_argument(
        "--format",
        choices=kmscn.IMAGE_FILE_FORMATS,
        default="RAW",
        help="device-requested image_file_format (RAW is required for local decoding)",
    )
    parser.add_argument("--resolution", choices=kmscn.SCAN_RESOLUTIONS)
    parser.add_argument("--color", choices=kmscn.COLOR_SELECTIONS)
    parser.add_argument("--duplex", choices=kmscn.DUPLEX_MODES)
    parser.add_argument(
        "--original-placement", choices=kmscn.ORIGINAL_PLACEMENTS
    )
    parser.add_argument(
        "--continuous-scan", choices=kmscn.CONTINUOUS_SCAN_MODES
    )
    parser.add_argument("--original-image", choices=kmscn.ORIGINAL_IMAGES)
    parser.add_argument("--operation-id")
    parser.add_argument("--retrieve-only", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    output_format = _local_format(
        args.decoded_output,
        args.no_decode,
        args.local_format,
    )
    if output_format == "raw":
        destination = args.output
    else:
        extension = {
            "jpeg": ".jpg",
            "tiff": ".tiff",
            "high_compression_pdf": ".pdf",
            "xps": ".xps",
        }.get(output_format, f".{output_format}")
        destination = args.decoded_output or args.output.with_suffix(
            extension
        )
    try:
        options = ScanOptions(
            color=args.color,
            resolution=args.resolution,
            original_image=args.original_image,
            duplex_mode=args.duplex,
            original_placement=args.original_placement,
            continuous_scan_mode=args.continuous_scan,
            output_format=output_format,
            max_pages=args.max_pages,
            max_polls=args.max_polls,
            poll_interval=args.poll_interval,
            timeout=args.timeout,
            insecure=args.insecure,
            max_response_bytes=args.max_response_bytes,
            https=args.https,
            port=args.port,
            device_file_format=args.format,
            operation_id=args.operation_id,
            retrieve_only=args.retrieve_only,
        )
        result = scan_device(args.target, options)
        paths = write_outputs(result, destination)
    except ScanError as error:
        payload = {"ok": False, **error.to_dict()}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(
                f"KM-WSDL scan failed at {error.stage}: {error.message}",
                file=sys.stderr,
            )
        return 1
    except (OSError, ValueError) as error:
        print(f"KM-WSDL scan failed: {error}", file=sys.stderr)
        return 2

    payload = result.metadata()
    payload["ok"] = True
    for output, path in zip(payload["outputs"], paths):
        output["path"] = str(path)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
