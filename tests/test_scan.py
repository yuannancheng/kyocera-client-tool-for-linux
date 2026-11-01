import base64
import io
import struct
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PIL import Image

from kyocera_monitor import kmscn, kmscn_raw, scan


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
            ),
        ),
        kmscn.XmlNode(
            "original_configuration",
            {},
            None,
            (kmscn.XmlNode("original_image", {}, "TEXT_AND_PHOTO", ()),),
        ),
        kmscn.XmlNode(
            "output_image_configuration",
            {},
            None,
            (kmscn.XmlNode("image_file_format", {}, "RAW", ()),),
        ),
    ),
)


def packet(
    command: int,
    subtype: int,
    color: int,
    width: int,
    height: int,
    data: bytes,
) -> bytes:
    header = (
        bytes((command, subtype, color))
        + width.to_bytes(2, "big")
        + height.to_bytes(2, "big")
    )
    return (7 + len(data)).to_bytes(4, "big") + header + data


def raw_rgb_stream() -> bytes:
    parts = []
    for color in (2, 3, 4):
        parts.append(packet(0x8A, 0x8A, color, 2, 2, bytes((10, 10, 10, 10))))
        parts.append(
            packet(0x8A, 0x8B, color, 2, 2, bytes((100, 100, 100, 100)))
        )
        parts.append(
            packet(0x82, 0x81, color, 2, 2, bytes((10, 100, 200, 50)))
        )
    parts.append(bytes.fromhex("0000000482820db3"))
    return b"".join(parts)


def response(
    operation: str,
    result: str,
    *,
    image: bytes | None = None,
    reported_file_size: int | None = None,
) -> kmscn.ScanResponse:
    encoded = base64.b64encode(image).decode("ascii") if image is not None else None
    return kmscn.ScanResponse(
        ok=True,
        operation=operation,
        endpoint="http://192.0.2.1:9090/scan",
        http_status=200,
        soap_version="1.2",
        result=result,
        operation_id="17",
        image_data=encoded,
        file_type="RAW" if image is not None else None,
        file_size=(
            reported_file_size
            if reported_file_size is not None
            else len(image) if image is not None else None
        ),
        content_type=None,
        body_length=0,
        fault_code=None,
        fault_reason=None,
    )


class FakeProtocol:
    def __init__(self, retrieve: list[kmscn.ScanResponse]):
        self.retrieve = iter(retrieve)
        self.started_configuration = None
        self.closed = False

    def build_endpoint(self, target, https, port):
        return target, f"http://{target}:9090{kmscn.SCAN_PATH}"

    def preflight(self, endpoint, **kwargs):
        return SimpleNamespace(ok=True, error=None, failed_stage=None)

    def probe_default_configuration(self, endpoint, **kwargs):
        return SimpleNamespace(ok=True, configuration=DEFAULT_CONFIGURATION)

    def set_configuration_value(self, node, name, value):
        return kmscn.set_configuration_value(node, name, value)

    def configuration_value(self, node, name):
        return kmscn.configuration_value(node, name)

    def open_session(self, endpoint, **kwargs):
        return response("open_session", "SUCCESS")

    def start_scan(self, endpoint, operation_id, configuration, **kwargs):
        self.started_configuration = configuration
        return response("start_scan", "SUCCESS")

    def retrieve_image(self, endpoint, operation_id, **kwargs):
        return next(self.retrieve)

    def close_session(self, endpoint, operation_id, **kwargs):
        self.closed = True
        return response("close_session", "SUCCESS")


class OptionTests(unittest.TestCase):
    def test_web_payload_uses_only_official_tokens(self):
        options = scan.ScanOptions.from_payload(
            {
                "color": "GRAYSCALE",
                "resolution": "RESOLUTION_300X300",
                "original_image": "PHOTO",
                "max_pages": 3,
                "output_format": "PDF",
            }
        )
        self.assertEqual(options.color, "GRAYSCALE")
        self.assertEqual(options.output_format, "pdf")
        self.assertEqual(options.max_pages, 3)

    def test_unknown_tokens_and_excessive_pages_are_rejected(self):
        with self.assertRaises(ValueError):
            scan.ScanOptions(color="COLOR")
        with self.assertRaises(ValueError):
            scan.ScanOptions(max_pages=11)
        with self.assertRaises(ValueError):
            scan.ScanOptions.from_payload({"output_format": "webp"})


class ExportTests(unittest.TestCase):
    def test_png_has_expected_signature_and_dimensions(self):
        decoded = kmscn_raw.DecodedScan(
            width=2,
            height=1,
            rgb=bytes((255, 0, 0, 0, 255, 0)),
            chunks=(),
        )
        png = scan.encode_png(decoded)
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(png[12:16], b"IHDR")
        self.assertEqual(struct.unpack(">II", png[16:24]), (2, 1))

    def test_pdf_contains_one_image_per_page(self):
        decoded = kmscn_raw.DecodedScan(
            width=2,
            height=1,
            rgb=bytes((255, 0, 0, 0, 255, 0)) * 2,
            chunks=(),
        )
        pdf = scan.encode_pdf([decoded, decoded], dpi=300)
        self.assertTrue(pdf.startswith(b"%PDF-1.4"))
        self.assertIn(b"/Count 2", pdf)
        self.assertEqual(pdf.count(b"/Subtype /Image"), 2)
        self.assertTrue(pdf.rstrip().endswith(b"%%EOF"))

    def test_jpeg_and_tiff_are_readable_images(self):
        decoded = kmscn_raw.DecodedScan(
            width=2,
            height=1,
            rgb=bytes((255, 0, 0, 0, 255, 0)),
            chunks=(),
        )
        jpeg = scan.encode_jpeg(decoded, quality=85, dpi=300)
        tiff = scan.encode_tiff([decoded, decoded], dpi=200)
        self.assertTrue(jpeg.startswith(b"\xff\xd8\xff"))
        self.assertEqual(tiff[:2], b"II")
        with Image.open(io.BytesIO(jpeg)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.size, (2, 1))
        with Image.open(io.BytesIO(tiff)) as image:
            self.assertEqual(image.format, "TIFF")
            self.assertEqual(image.n_frames, 2)

    def test_high_compression_pdf_uses_jpeg_image_streams(self):
        decoded = kmscn_raw.DecodedScan(
            width=2,
            height=1,
            rgb=bytes((255, 0, 0, 0, 255, 0)),
            chunks=(),
        )
        pdf = scan.encode_pdf([decoded], high_compression=True)
        self.assertIn(b"/DCTDecode", pdf)
        self.assertNotIn(b"/FlateDecode", pdf)

    def test_xps_package_contains_pages_and_images(self):
        decoded = kmscn_raw.DecodedScan(
            width=2,
            height=1,
            rgb=bytes((255, 0, 0, 0, 255, 0)),
            chunks=(),
        )
        xps = scan.encode_xps([decoded, decoded], dpi=300)
        with zipfile.ZipFile(io.BytesIO(xps)) as archive:
            names = set(archive.namelist())
            self.assertIn("[Content_Types].xml", names)
            self.assertIn("Documents/1/FixedDocument.fdoc", names)
            self.assertIn("Documents/1/Pages/1.fpage", names)
            self.assertIn("Documents/1/Pages/2.fpage", names)
            self.assertTrue(
                archive.read("Resources/Images/1.jpg").startswith(b"\xff\xd8\xff")
            )

    def test_multiple_pages_export_as_separate_png_files(self):
        decoded = kmscn_raw.DecodedScan(
            width=2,
            height=1,
            rgb=bytes((1, 2, 3, 4, 5, 6)),
            chunks=(),
        )
        outputs = scan.export_pages(
            [decoded, decoded],
            raw_pages=[b"one", b"two"],
            output_format="png",
            output_stem="scan",
            resolution=None,
        )
        self.assertEqual(
            [output.filename for output in outputs],
            ["scan-1.png", "scan-2.png"],
        )

    def test_write_outputs_is_atomic_for_one_file(self):
        artifact = scan.ScanArtifact(
            filename="scan.png",
            media_type="image/png",
            kind="png",
            width=1,
            height=1,
            data=b"png",
        )
        result = scan.ScanResult(
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
            target = Path(tmp) / "chosen.png"
            written = scan.write_outputs(result, target)
            self.assertEqual(written, (target,))
            self.assertEqual(target.read_bytes(), b"png")

    def test_write_output_failure_removes_temporary_file(self):
        artifact = scan.ScanArtifact(
            filename="scan.png",
            media_type="image/png",
            kind="png",
            width=1,
            height=1,
            data=b"png",
        )
        result = scan.ScanResult(
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
            with self.assertRaises(OSError):
                scan.write_outputs(result, Path(tmp))
            self.assertEqual(list(Path(tmp).iterdir()), [])


class WorkflowTests(unittest.TestCase):
    def test_scan_applies_overrides_exports_and_closes_session(self):
        raw = raw_rgb_stream()
        protocol = FakeProtocol(
            [
                response("retrieve_image", "IMAGE_CREATING_NOW"),
                response("retrieve_image", "SUCCESS", image=raw),
                response("retrieve_image", "ALL_GET_COMPLETE"),
            ]
        )
        stages = []
        result = scan.scan_device(
            "192.0.2.1",
            scan.ScanOptions(
                color="GRAYSCALE",
                resolution="RESOLUTION_200X200",
                original_image="PHOTO",
                output_format="png",
                poll_interval=0,
            ),
            protocol=protocol,
            progress=lambda stage, message: stages.append(stage),
            sleep=lambda _seconds: None,
        )

        self.assertEqual(result.pages, 1)
        self.assertEqual(result.outputs[0].kind, "png")
        self.assertEqual(result.outputs[0].width, 2)
        self.assertEqual(result.close_result, "SUCCESS")
        self.assertTrue(protocol.closed)
        self.assertIn("retrieve_image", stages)
        self.assertIn("decode_raw", stages)
        rendered = kmscn._render_xml_node(protocol.started_configuration)
        self.assertIn(
            "<kmscn:color_selection>GRAYSCALE</kmscn:color_selection>",
            rendered,
        )
        self.assertIn(
            "<kmscn:scan_resolution>RESOLUTION_200X200</kmscn:scan_resolution>",
            rendered,
        )
        self.assertIn(
            "<kmscn:original_image>PHOTO</kmscn:original_image>",
            rendered,
        )
        self.assertIn(
            "<kmscn:image_file_format>RAW</kmscn:image_file_format>",
            rendered,
        )

    def test_decode_failure_still_closes_session(self):
        protocol = FakeProtocol(
            [
                response("retrieve_image", "SUCCESS", image=b"not-raw"),
                response("retrieve_image", "ALL_GET_COMPLETE"),
            ]
        )
        with self.assertRaises(scan.ScanError) as caught:
            scan.scan_device(
                "192.0.2.1",
                scan.ScanOptions(poll_interval=0),
                protocol=protocol,
                sleep=lambda _seconds: None,
            )
        self.assertEqual(caught.exception.stage, "decode_raw")
        self.assertTrue(protocol.closed)

    def test_reported_file_size_is_not_used_as_transfer_length(self):
        raw = raw_rgb_stream()
        protocol = FakeProtocol(
            [
                response(
                    "retrieve_image",
                    "SUCCESS",
                    image=raw,
                    reported_file_size=4,
                ),
                response("retrieve_image", "ALL_GET_COMPLETE"),
            ]
        )
        result = scan.scan_device(
            "192.0.2.1",
            scan.ScanOptions(poll_interval=0),
            protocol=protocol,
            sleep=lambda _seconds: None,
        )
        self.assertEqual(result.pages, 1)
        self.assertGreater(len(raw), 4)
        self.assertTrue(protocol.closed)

    def test_poll_timeout_is_actionable_and_closes_session(self):
        protocol = FakeProtocol(
            [
                response("retrieve_image", "IMAGE_CREATING_NOW"),
                response("retrieve_image", "IMAGE_CREATING_NOW"),
            ]
        )
        with self.assertRaises(scan.ScanError) as caught:
            scan.scan_device(
                "192.0.2.1",
                scan.ScanOptions(max_polls=2, poll_interval=0),
                protocol=protocol,
                sleep=lambda _seconds: None,
            )
        self.assertEqual(caught.exception.stage, "retrieve_image")
        self.assertIn("2", caught.exception.message)
        self.assertTrue(protocol.closed)

    def test_adf_scan_handles_two_pages_and_completion(self):
        raw = raw_rgb_stream()
        protocol = FakeProtocol(
            [
                response("retrieve_image", "CONTINUE_SCAN"),
                response("retrieve_image", "SUCCESS", image=raw),
                response("retrieve_image", "SUCCESS", image=raw),
                response("retrieve_image", "ALL_GET_COMPLETE"),
            ]
        )
        result = scan.scan_device(
            "192.0.2.1",
            scan.ScanOptions(
                duplex_mode="BOOKLET",
                original_placement="ADF",
                continuous_scan_mode="ON",
                output_format="bmp",
                max_pages=2,
                poll_interval=0,
            ),
            protocol=protocol,
            sleep=lambda _seconds: None,
        )
        self.assertEqual(result.pages, 2)
        prefix = result.outputs[0].filename.rsplit("-", 1)[0]
        self.assertEqual(
            [output.filename for output in result.outputs],
            [f"{prefix}-1.bmp", f"{prefix}-2.bmp"],
        )
        rendered = kmscn._render_xml_node(protocol.started_configuration)
        self.assertIn(
            "<kmscn:duplex_mode>BOOKLET</kmscn:duplex_mode>", rendered
        )
        self.assertIn(
            "<kmscn:original_placement>ADF</kmscn:original_placement>",
            rendered,
        )
        self.assertIn(
            "<kmscn:continuous_scan_mode>ON</kmscn:continuous_scan_mode>",
            rendered,
        )

    def test_busy_device_rejects_parallel_job(self):
        release = threading.Event()

        def runner(device, options, progress):
            release.wait(timeout=2)
            return mock.Mock()

        manager = scan.ScanJobManager(runner)
        first = manager.start("192.0.2.1", scan.ScanOptions())
        with self.assertRaises(scan.ScanBusyError):
            manager.start("192.0.2.1", scan.ScanOptions())
        release.set()
        manager.wait(first.job_id)

    def test_device_can_scan_again_after_completion(self):
        result = scan.ScanResult(
            device="192.0.2.1",
            endpoint="http://192.0.2.1:9090/scan",
            operation_id="17",
            pages=1,
            requested_device_format="RAW",
            effective_device_format="RAW",
            outputs=(),
            close_result="SUCCESS",
            close_error=None,
        )
        manager = scan.ScanJobManager(lambda *_args, **_kwargs: result)
        first = manager.start("192.0.2.1", scan.ScanOptions())
        manager.wait(first.job_id)
        second = manager.start("192.0.2.1", scan.ScanOptions())
        manager.wait(second.job_id)
        self.assertNotEqual(first.job_id, second.job_id)


if __name__ == "__main__":
    unittest.main()
