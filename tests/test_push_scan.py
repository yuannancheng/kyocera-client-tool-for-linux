import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from kyocera_monitor import cli
from kyocera_monitor.push_scan import (
    PUSH_SCAN_OIDS,
    interpret_push_scan,
    read_push_scan,
)
from kyocera_monitor.snmp import VarBind
from kyocera_monitor.web import DEVICE_HTML, DeviceRegistry, make_handler


LOCAL_IDENTITY = {
    "addresses": ["192.168.0.50", "2001:db8::50"],
    "host_names": ["workstation", "workstation.example.test"],
}


def bind(name: str, tag: int, value: object) -> VarBind:
    return VarBind(PUSH_SCAN_OIDS[name], tag, value)


def push_scan_values(
    *,
    interface: int = 1,
    address_type: int = 1,
    ipv4: bytes = bytes([192, 168, 0, 50]),
    ipv6: bytes = bytes(16),
    host_name: bytes = b"",
    result: int = 0,
):
    return [
        bind("interface", 0x02, interface),
        bind("ipv4_address", 0x40, ipv4),
        bind("result", 0x02, result),
        bind("ipv6_address", 0x04, ipv6),
        bind("host_name", 0x04, host_name),
        bind("address_type", 0x02, address_type),
    ]


class PushScanInterpretationTests(unittest.TestCase):
    def test_network_ipv4_target_is_ready_for_this_computer(self):
        result = interpret_push_scan(
            push_scan_values(),
            host="192.168.0.220",
            local_identity=LOCAL_IDENTITY,
        )
        self.assertTrue(result["read_only"])
        self.assertEqual(result["interface"]["name"], "NETWORK")
        self.assertEqual(result["address_type"]["name"], "IPv4")
        self.assertEqual(result["target"], "192.168.0.50")
        self.assertTrue(result["target_matches_local"])
        self.assertTrue(result["readiness"]["ready"])
        self.assertEqual(result["readiness"]["state"], "ready")
        self.assertFalse(result["execution"]["supported"])

    def test_usb_destination_is_not_network_ready(self):
        result = interpret_push_scan(
            push_scan_values(interface=0),
            host="192.168.0.220",
            local_identity=LOCAL_IDENTITY,
        )
        self.assertFalse(result["readiness"]["ready"])
        self.assertEqual(result["readiness"]["state"], "usb_destination")

    def test_unset_network_target_is_not_configured(self):
        result = interpret_push_scan(
            push_scan_values(ipv4=bytes(4)),
            host="192.168.0.220",
            local_identity=LOCAL_IDENTITY,
        )
        self.assertEqual(result["target"], "0.0.0.0")
        self.assertFalse(result["target_matches_local"])
        self.assertEqual(result["readiness"]["state"], "not_configured")

    def test_target_on_other_host_is_reported_without_writing(self):
        result = interpret_push_scan(
            push_scan_values(ipv4=bytes([192, 168, 0, 51])),
            host="192.168.0.220",
            local_identity=LOCAL_IDENTITY,
        )
        self.assertFalse(result["target_matches_local"])
        self.assertEqual(result["readiness"]["state"], "other_host")

    def test_ipv6_and_hostname_targets_use_the_official_address_type(self):
        ipv6 = interpret_push_scan(
            push_scan_values(
                address_type=2,
                ipv6=bytes.fromhex("20010db8000000000000000000000050"),
            ),
            host="192.168.0.220",
            local_identity=LOCAL_IDENTITY,
        )
        self.assertEqual(ipv6["target"], "2001:db8::50")
        self.assertEqual(ipv6["readiness"]["state"], "ready")

        hostname = interpret_push_scan(
            push_scan_values(
                address_type=3,
                host_name=b"Workstation.Example.Test",
            ),
            host="192.168.0.220",
            local_identity=LOCAL_IDENTITY,
        )
        self.assertEqual(hostname["target"], "Workstation.Example.Test")
        self.assertEqual(hostname["readiness"]["state"], "ready")

    def test_missing_interface_is_reported_as_unavailable(self):
        values = [
            item for item in push_scan_values() if item.oid != PUSH_SCAN_OIDS["interface"]
        ]
        result = interpret_push_scan(
            values,
            host="192.168.0.220",
            local_identity=LOCAL_IDENTITY,
        )
        self.assertFalse(result["objects"]["interface"]["available"])
        self.assertEqual(result["readiness"]["state"], "unavailable")
        self.assertIsNone(result["readiness"]["ready"])

    def test_last_result_is_explicitly_historical(self):
        result = interpret_push_scan(
            push_scan_values(result=1),
            host="192.168.0.220",
            local_identity=LOCAL_IDENTITY,
        )
        self.assertEqual(result["last_result"]["name"], "NG")
        self.assertEqual(
            result["last_result"]["scope"],
            "last_reported_result",
        )


class PushScanReadTests(unittest.TestCase):
    def test_read_uses_one_read_only_snmp_get(self):
        client = mock.Mock()
        client.get.return_value = push_scan_values()
        with mock.patch(
            "kyocera_monitor.push_scan.SnmpClient",
            return_value=client,
        ) as factory:
            result = read_push_scan(
                "192.168.0.220",
                community="private",
                version="2c",
                local_identity=LOCAL_IDENTITY,
            )
        factory.assert_called_once()
        client.get.assert_called_once()
        self.assertEqual(
            list(client.get.call_args.args[0]),
            list(PUSH_SCAN_OIDS.values()),
        )
        self.assertEqual(result["readiness"]["state"], "ready")
        client.set_integer.assert_not_called()


class PushScanCliTests(unittest.TestCase):
    def test_cli_prints_json_and_does_not_write(self):
        payload = interpret_push_scan(
            push_scan_values(),
            host="192.168.0.220",
            local_identity=LOCAL_IDENTITY,
        )
        with mock.patch.object(cli, "read_push_scan", return_value=payload) as read:
            output = io.StringIO()
            with redirect_stdout(output), redirect_stderr(io.StringIO()):
                code = cli.main(
                    [
                        "--host",
                        "192.168.0.220",
                        "--push-scan",
                        "--snmp-version",
                        "2c",
                        "--json",
                    ]
                )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["readiness"]["state"], "ready")
        read.assert_called_once()
        self.assertEqual(read.call_args.kwargs["version"], "2c")


class PushScanWebTests(unittest.TestCase):
    def setUp(self):
        registry = DeviceRegistry(
            lambda _key: None,
            "192.168.0.220",
            min_interval=0,
        )
        self.reader = mock.Mock(
            return_value=interpret_push_scan(
                push_scan_values(),
                host="192.168.0.220",
                local_identity=LOCAL_IDENTITY,
            )
        )
        self.handler = make_handler(
            registry,
            push_scan_reader=self.reader,
        )

    def request(self, path):
        request = self.handler.__new__(self.handler)
        request.path = path
        request.headers = {}
        request.rfile = io.BytesIO()
        request.wfile = io.BytesIO()
        request._status = None

        request.send_response = lambda status: setattr(request, "_status", status)
        request.send_header = lambda _name, _value: None
        request.end_headers = lambda: None
        request.log_message = lambda *_args: None
        request.do_GET()
        return request._status, request.wfile.getvalue()

    def test_api_returns_read_only_readiness(self):
        status, body = self.request("/api/push-scan?host=192.168.0.220")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["readiness"]["state"], "ready")
        self.reader.assert_called_once_with("192.168.0.220")

    def test_device_page_has_push_scan_read_action_only(self):
        self.assertIn("/api/push-scan", DEVICE_HTML)
        self.assertIn('id="push-scan-read"', DEVICE_HTML)
        self.assertIn('id="push-scan-grid"', DEVICE_HTML)
        self.assertNotIn("/api/push-scan/execute", DEVICE_HTML)
        self.assertIn(".push-result.ready { color: #145014; }", DEVICE_HTML)
        self.assertIn(".push-result.ready { color: #d3f2d8; }", DEVICE_HTML)


if __name__ == "__main__":
    unittest.main()
