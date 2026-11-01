import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from kyocera_monitor.scan import ScanArtifact, ScanResult


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "tools" / "kmscn_scan.py"
SPEC = importlib.util.spec_from_file_location("kmscn_scan", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load tools/kmscn_scan.py")
kmscn_scan = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = kmscn_scan
SPEC.loader.exec_module(kmscn_scan)


class CompatibilityWrapperTests(unittest.TestCase):
    def test_legacy_cli_delegates_to_integrated_service(self):
        artifact = ScanArtifact(
            filename="scan.png",
            media_type="image/png",
            kind="png",
            width=2,
            height=2,
            data=b"png-data",
        )
        result = ScanResult(
            device="192.0.2.1",
            endpoint="http://192.0.2.1:9090/scan",
            operation_id="17",
            pages=1,
            requested_device_format="RAW",
            effective_device_format="RAW",
            outputs=(artifact,),
            close_result="SUCCESS",
            close_error=None,
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "scan.png"
            with mock.patch.object(
                kmscn_scan,
                "scan_device",
                return_value=result,
            ) as run, redirect_stdout(io.StringIO()) as stdout:
                exit_code = kmscn_scan.main(
                    [
                        "192.0.2.1",
                        "--decoded-output",
                        str(output),
                        "--color",
                        "GRAYSCALE",
                        "--max-pages",
                        "2",
                        "--json",
                    ]
                )

            options = run.call_args.args[1]
            self.assertEqual(exit_code, 0)
            self.assertEqual(options.output_format, "png")
            self.assertEqual(options.color, "GRAYSCALE")
            self.assertEqual(options.max_pages, 2)
            self.assertEqual(output.read_bytes(), b"png-data")
            payload = json.loads(stdout.getvalue())
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["outputs"][0]["path"], str(output))


if __name__ == "__main__":
    unittest.main()
