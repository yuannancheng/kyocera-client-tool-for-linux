import unittest
from types import SimpleNamespace
from unittest import mock

from kyocera_monitor.cli import usb_scan_parameters_from_cli
from kyocera_monitor.usb_scan import (
    UsbScanError,
    UsbScanParameters,
    UsbScannerControl,
    build_scan_request,
    build_version_request,
    parse_control_response,
    parse_machine_info,
    parse_packet,
    parse_scan_ack,
    parse_version,
)


class UsbScanProtocolTests(unittest.TestCase):
    @staticmethod
    def _frame(command: int, status: int, body: bytes = b"") -> bytes:
        payload = bytes((command, status)) + body
        return len(payload).to_bytes(4, "big") + payload

    def test_version_request_matches_official_ma2000w_packet(self):
        self.assertEqual(
            build_version_request(),
            b"\x00\x00\x00\x07\x22\x00\x0a001\x0a",
        )

    def test_machine_info_response_is_parsed_from_declared_length(self):
        body = b"\nT=OFF\nC=2160,2970\nD=30,25,30,40\nP=20,20,20,20"
        raw = (
            (len(body) + 2).to_bytes(4, "big")
            + b"\x21\x80"
            + body
            + b"\x00" * 20
        )
        values = parse_machine_info(raw)["raw"]
        self.assertEqual(values["T"], "OFF")
        self.assertEqual(values["C"], "2160,2970")
        self.assertEqual(values["D"], "30,25,30,40")
        self.assertEqual(values["P"], "20,20,20,20")

    def test_version_response_is_parsed(self):
        raw = b"\x00\x00\x00\x06\x22\x80\n000\n"
        self.assertEqual(parse_version(raw), 0)

    def test_scan_request_matches_the_recovered_serializer(self):
        raw = build_scan_request()
        self.assertEqual(int.from_bytes(raw[:4], "big"), len(raw) - 4)
        self.assertEqual(raw[4:6], b"\x81\x00")
        self.assertEqual(
            raw[6:],
            (
                b"\nR=A4Y\nX=300X300\nM=COLOR\nQ=TEXT+PHOTO\nD=0\n"
                b"U=OFF\nF=AUTO\nP=CNT\nS=Low\nB=SIMPLEX\n"
                b"N=LEFTRIGHT\nO=Top Edge Left\nE=OFF\n"
                b"A=d,0,0,0\n%d,%d,%d,%d"
            ),
        )

    def test_scan_request_encodes_area_duplex_and_supported_tokens(self):
        raw = build_scan_request(
            UsbScanParameters(
                original_size=1,
                feed_method=2,
                resolution=600,
                color_mode=2,
                original_image=1,
                density=-3,
                reverse_image=1,
                orientation=3,
                page_mode=2,
                scan_area=(10, 20, 30, 40),
                duplex=1,
                duplex_edge=1,
                sharpen=3,
            )
        )
        text = raw[6:].decode("ascii")
        self.assertIn("\nR=LETTER\n", text)
        self.assertIn("\nX=600X600\n", text)
        self.assertIn("\nM=GRAY\n", text)
        self.assertIn("\nQ=TEXT\n", text)
        self.assertIn("\nD=-3\n", text)
        self.assertIn("U=ON\n", text)
        self.assertIn("F=DP\n", text)
        self.assertIn("P=STEP\n", text)
        self.assertIn("S=High\n", text)
        self.assertIn("B=DUPLEX\n", text)
        self.assertIn("N=TOP\n", text)
        self.assertIn("O=Top Edge Top\n", text)
        self.assertIn("E=ON\n", text)
        self.assertIn("A=d,10,20,30\n%d,%d,%d,%d", text)

    def test_scan_request_rejects_values_outside_recovered_tables(self):
        with self.assertRaises(UsbScanError):
            build_scan_request(UsbScanParameters(resolution=123))
        with self.assertRaises(UsbScanError):
            build_scan_request(UsbScanParameters(color_mode=9))
        with self.assertRaises(ValueError):
            build_scan_request(UsbScanParameters(scan_area=(0, 0, 0)))

    def test_scan_ack_maps_recovered_status_codes(self):
        self.assertEqual(
            parse_scan_ack(b"\x00\x00\x00\x02\x81\x80").result,
            "success",
        )
        platen = parse_scan_ack(b"\x00\x00\x00\x02\x81\x8a")
        self.assertEqual(platen.source, "platen")
        retry = parse_scan_ack(b"\x00\x00\x00\x02\x81\x81")
        self.assertTrue(retry.retryable)
        no_original = parse_scan_ack(b"\x00\x00\x00\x02\x81\x82")
        self.assertEqual(no_original.result, "no_original")
        with self.assertRaises(UsbScanError):
            parse_scan_ack(b"\x00\x00\x00\x02\x82\x80")
        with self.assertRaises(UsbScanError):
            parse_scan_ack(b"\x00")

    def test_control_session_sends_only_recovered_requests(self):
        scanner = object.__new__(UsbScannerControl)
        scanner.bulk_out = mock.Mock()
        scanner.bulk_in = mock.Mock(
            return_value=b"\x00\x00\x00\x02\x81\x8a"
        )
        scanner.control_in = mock.Mock(
            side_effect=[
                b"\x00\x00\x00\x02\x82\x80",
                b"\x00\x00\x00\x02\x83\x80",
            ]
        )

        ack = scanner.start_scan(
            UsbScanParameters(color_mode=2, original_image=1)
        )

        self.assertEqual(ack.source, "platen")
        scanner.bulk_out.assert_called_once()
        self.assertIn(b"\nM=GRAY\n", scanner.bulk_out.call_args.args[0])
        self.assertEqual(
            scanner.page_data(),
            b"\x00\x00\x00\x02\x82\x80",
        )
        self.assertEqual(
            scanner.end_job(),
            b"\x00\x00\x00\x02\x83\x80",
        )
        self.assertEqual(
            [call.args[0] for call in scanner.control_in.call_args_list],
            [0x82, 0x83],
        )

    def test_capture_page_handles_fragmented_frames_and_keeps_image_frames(self):
        page_info = self._frame(0x82, 0x84, b"\nO=NONE\nR=A4,0\n")
        calibration = self._frame(0x8A, 0x8A, b"\x01x" + b"\x00" * 8)
        band = self._frame(0x82, 0x81, b"\x01x" + b"\x00" * 8)
        page_end = self._frame(0x7E, 0x7E)
        stream = page_info + calibration + band + page_end
        chunks = [
            stream[:3],
            stream[3:9],
            stream[9:17],
            stream[17:31],
            stream[31:],
        ]
        scanner = object.__new__(UsbScannerControl)
        scanner.bulk_out = mock.Mock()
        scanner.bulk_in = mock.Mock(
            side_effect=[
                b"\x00\x00\x00\x02\x81\x8a",
                *chunks,
            ]
        )
        scanner.control_in = mock.Mock(
            side_effect=[
                b"\x00\x00\x00\x02\x82\x80",
                b"\x00\x00\x00\x02\x83\x80",
            ]
        )

        page = scanner.capture_page()

        self.assertEqual(page.terminator, "page")
        self.assertEqual(page.raw, calibration + band)
        self.assertEqual(page.scan_ack.source, "platen")
        self.assertEqual(page.job_end_response[4:], b"\x83\x80")
        self.assertEqual(
            [call.args[0] for call in scanner.control_in.call_args_list],
            [0x82, 0x83],
        )

    def test_cli_tokens_map_to_recovered_scan_parameters(self):
        args = SimpleNamespace(
            scan_color="GRAYSCALE",
            scan_resolution="RESOLUTION_600X600",
            scan_original_image="TEXT",
            scan_original_placement="PLATEN",
            scan_duplex="DUPLEX",
            scan_continuous="OFF",
            scan_max_pages=1,
            scan_device_format="RAW",
        )

        parameters = usb_scan_parameters_from_cli(args)

        self.assertEqual(parameters.feed_method, 3)
        self.assertEqual(parameters.resolution, 600)
        self.assertEqual(parameters.color_mode, 2)
        self.assertEqual(parameters.original_image, 1)
        self.assertEqual(parameters.duplex, 1)
        self.assertEqual(parameters.duplex_edge, 0)

    def test_cli_rejects_unmodeled_usb_scan_tokens(self):
        args = SimpleNamespace(
            scan_color="AUTO_GRAYSCALE",
            scan_resolution=None,
            scan_original_image=None,
            scan_original_placement=None,
            scan_duplex=None,
            scan_continuous=None,
            scan_max_pages=1,
            scan_device_format="RAW",
        )

        with self.assertRaises(UsbScanError):
            usb_scan_parameters_from_cli(args)

    def test_control_responses_check_command_and_status(self):
        self.assertEqual(
            parse_control_response(
                b"\x00\x00\x00\x02\x41\x80",
                request=0x41,
                success_codes=(0x80,),
            ),
            b"\x00\x00\x00\x02\x41\x80",
        )
        with self.assertRaises(UsbScanError):
            parse_control_response(
                b"\x00\x00\x00\x02\x42\x80",
                request=0x41,
                success_codes=(0x80,),
            )
        with self.assertRaises(UsbScanError):
            parse_control_response(
                b"\x00\x00\x00\x02\x41\x90",
                request=0x41,
                success_codes=(0x80,),
            )

    def test_malformed_frames_fail_closed(self):
        with self.assertRaises(UsbScanError):
            parse_packet(b"\x00\x00")
        with self.assertRaises(UsbScanError):
            parse_packet(b"\x00\x00\x00\x20\x21\x80")
        with self.assertRaises(ValueError):
            build_version_request(b"12")


if __name__ == "__main__":
    unittest.main()
