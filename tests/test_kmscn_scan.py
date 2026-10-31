import base64
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from kyocera_monitor import kmscn


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "tools" / "kmscn_scan.py"
SPEC = importlib.util.spec_from_file_location("kmscn_scan", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load tools/kmscn_scan.py")
kmscn_scan = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = kmscn_scan
SPEC.loader.exec_module(kmscn_scan)


DEFAULT_CONFIGURATION = kmscn.XmlNode(
    "get_default_configurationResponse",
    {},
    None,
    (
        kmscn.XmlNode("result", {}, "SUCCESS", ()),
        kmscn.XmlNode(
            "scan_image_configuration",
            {},
            None,
            (
                kmscn.XmlNode("color_selection", {}, "FULL_COLOR", ()),
                kmscn.XmlNode(
                    "scan_resolution",
                    {},
                    "RESOLUTION_300X300",
                    (),
                ),
                kmscn.XmlNode("duplex_mode", {}, "SIMPLEX", ()),
            ),
        ),
        kmscn.XmlNode(
            "original_configuration",
            {},
            None,
            (
                kmscn.XmlNode("original_image", {}, "TEXT_AND_PHOTO", ()),
                kmscn.XmlNode("original_size", {}, "A4", ()),
                kmscn.XmlNode("original_placement", {}, "AUTO", ()),
            ),
        ),
        kmscn.XmlNode(
            "output_image_configuration",
            {},
            None,
            (kmscn.XmlNode("image_file_format", {}, "RAW", ()),),
        ),
    ),
)


def scan_response(
    result: str,
    *,
    image_data: bytes | None = None,
) -> kmscn.ScanResponse:
    encoded = (
        base64.b64encode(image_data).decode("ascii")
        if image_data is not None
        else None
    )
    return kmscn.ScanResponse(
        ok=True,
        operation="retrieve_image",
        endpoint="http://192.0.2.1:9090/scan",
        http_status=200,
        soap_version="1.2",
        result=result,
        operation_id="17",
        image_data=encoded,
        file_type="RAW",
        file_size=len(image_data) if image_data is not None else None,
        content_type=None,
        body_length=0,
        fault_code=None,
        fault_reason=None,
    )


class PaginationTests(unittest.TestCase):
    def test_adf_duplex_continuous_options_and_two_pages(self):
        started_configuration = {}

        def capture_start(_endpoint, _operation_id, configuration, **_kwargs):
            started_configuration["value"] = configuration
            return SimpleNamespace(ok=True)

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "scan.raw"
            with mock.patch.object(
                kmscn_scan.kmscn,
                "preflight",
                return_value=SimpleNamespace(ok=True),
            ), mock.patch.object(
                kmscn_scan.kmscn,
                "probe_default_configuration",
                return_value=SimpleNamespace(
                    ok=True,
                    configuration=DEFAULT_CONFIGURATION,
                ),
            ), mock.patch.object(
                kmscn_scan.kmscn,
                "open_session",
                return_value=SimpleNamespace(ok=True, operation_id="17"),
            ), mock.patch.object(
                kmscn_scan.kmscn,
                "start_scan",
                side_effect=capture_start,
            ), mock.patch.object(
                kmscn_scan.kmscn,
                "retrieve_image",
                side_effect=(
                    scan_response("CONTINUE_SCAN"),
                    scan_response("SUCCESS", image_data=b"first-page"),
                    scan_response("SUCCESS", image_data=b"second-page"),
                    scan_response("ALL_GET_COMPLETE"),
                ),
            ), mock.patch.object(
                kmscn_scan.kmscn,
                "close_session",
                return_value=SimpleNamespace(ok=True, result="SUCCESS"),
            ), mock.patch.object(
                kmscn_scan.time,
                "sleep",
            ), redirect_stdout(io.StringIO()) as stdout:
                exit_code = kmscn_scan.main(
                    [
                        "192.0.2.1",
                        "--max-pages",
                        "2",
                        "--no-decode",
                        "--duplex",
                        "BOOKLET",
                        "--original-placement",
                        "ADF",
                        "--continuous-scan",
                        "ON",
                        "--output",
                        str(output),
                        "--json",
                    ]
                )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertTrue(payload["completed"])
            self.assertEqual(payload["close_result"], "SUCCESS")
            self.assertEqual(
                payload["configuration_overrides"],
                {
                    "duplex_mode": "BOOKLET",
                    "original_placement": "ADF",
                    "continuous_scan_mode": "ON",
                },
            )
            self.assertEqual(
                [item["bytes"] for item in payload["outputs"]],
                [len(b"first-page"), len(b"second-page")],
            )
            self.assertEqual(
                [item["file_type"] for item in payload["outputs"]],
                ["RAW", "RAW"],
            )
            self.assertEqual(
                (Path(tmp) / "scan-1.raw").read_bytes(),
                b"first-page",
            )
            self.assertEqual(
                (Path(tmp) / "scan-2.raw").read_bytes(),
                b"second-page",
            )

        rendered = kmscn._render_xml_node(started_configuration["value"])
        self.assertIn(
            "<kmscn:duplex_mode>BOOKLET</kmscn:duplex_mode>",
            rendered,
        )
        self.assertIn(
            "<kmscn:original_placement>ADF</kmscn:original_placement>",
            rendered,
        )
        self.assertIn(
            "<kmscn:continuous_scan_mode>ON</kmscn:continuous_scan_mode>",
            rendered,
        )
        self.assertLess(
            rendered.index("<kmscn:scan_resolution>"),
            rendered.index("<kmscn:continuous_scan_mode>"),
        )
        self.assertLess(
            rendered.index("<kmscn:continuous_scan_mode>"),
            rendered.index("<kmscn:duplex_mode>"),
        )


if __name__ == "__main__":
    unittest.main()
