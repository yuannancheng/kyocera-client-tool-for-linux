import io
import json
import socket
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from kyocera_monitor import cli, discovery
from kyocera_monitor.discovery import DiscoveredPrinter
from kyocera_monitor.snmp import VarBind


class ArpTests(unittest.TestCase):
    def test_reads_only_resolved_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "arp"
            path.write_text(
                "IP address       HW type     Flags       HW address            Mask     Device\n"
                "192.168.0.220    0x1         0x2         00:11:22:33:44:55     *        eth0\n"
                "192.168.0.50     0x1         0x0         00:00:00:00:00:00     *        eth0\n",
                encoding="ascii",
            )
            self.assertEqual(
                discovery.arp_candidates(str(path)), ["192.168.0.220"]
            )

    def test_missing_arp_file_is_not_fatal(self):
        self.assertEqual(discovery.arp_candidates("/nonexistent/arp"), [])


class SubnetTests(unittest.TestCase):
    def test_small_network_expands_hosts_and_broadcast(self):
        hosts, broadcast = discovery.subnet_candidates("192.168.0.0/30")
        self.assertEqual(hosts, ["192.168.0.1", "192.168.0.2"])
        self.assertEqual(broadcast, "192.168.0.3")

    def test_large_network_is_rejected(self):
        with self.assertRaises(ValueError):
            discovery.subnet_candidates("10.0.0.0/8")


class MappingTests(unittest.TestCase):
    def test_varbinds_become_printer_identity(self):
        printer = discovery.printer_from_varbinds(
            "192.168.0.220",
            [
                VarBind(discovery.MODEL_OID, 0x04, b"MA2000w"),
                VarBind(discovery.SERIAL_OID, 0x04, b"H4933\x00"),
                VarBind(discovery.FIRMWARE_OID, 0x04, b"2YW_2000.001.101"),
            ],
            "snmp-unicast",
        )
        self.assertEqual(printer.model, "MA2000w")
        self.assertEqual(printer.serial, "H4933")
        self.assertEqual(printer.firmware, "2YW_2000.001.101")
        self.assertEqual(printer.sources, ["snmp-unicast"])

    def test_missing_model_is_not_a_kyocera_printer(self):
        printer = discovery.printer_from_varbinds(
            "192.0.2.1",
            [VarBind(discovery.SERIAL_OID, 0x04, b"SERIAL")],
            "snmp-unicast",
        )
        self.assertIsNone(printer)

    def test_merge_unions_sources_and_fills_gaps(self):
        left = DiscoveredPrinter(
            "192.168.0.220", model="MA2000w", sources=["snmp-broadcast"]
        )
        right = DiscoveredPrinter(
            "192.168.0.220",
            model="MA2000w",
            serial="S",
            sources=["snmp-unicast"],
            xaddrs=["http://192.168.0.220:5357/"],
        )
        left.merge(right)
        self.assertEqual(left.serial, "S")
        self.assertEqual(left.sources, ["snmp-broadcast", "snmp-unicast"])
        self.assertEqual(left.xaddrs, ["http://192.168.0.220:5357/"])


class WsdTests(unittest.TestCase):
    XML = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
 xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
 xmlns:wsd="http://schemas.xmlsoap.org/ws/2005/04/discovery">
 <soap:Body><wsd:ProbeMatches><wsd:ProbeMatch>
  <wsa:EndpointReference><wsa:Address>urn:uuid:test</wsa:Address></wsa:EndpointReference>
  <wsd:Types>wsdp:Device print:PrintDeviceType</wsd:Types>
  <wsd:Scopes>onvif://www.onvif.org/type/NetworkVideoTransmitter</wsd:Scopes>
  <wsd:XAddrs>http://192.168.0.220:5357/abc/</wsd:XAddrs>
 </wsd:ProbeMatch></wsd:ProbeMatches></soap:Body>
</soap:Envelope>"""

    def test_summarize_extracts_discovery_fields(self):
        fields = discovery.summarize_wsd(self.XML)
        self.assertEqual(fields["endpoint"], ["urn:uuid:test"])
        self.assertEqual(fields["xaddrs"], ["http://192.168.0.220:5357/abc/"])
        self.assertEqual(fields["types"], ["wsdp:Device print:PrintDeviceType"])
        self.assertEqual(len(fields["scopes"]), 1)

    def test_socket_error_returns_no_results(self):
        with mock.patch.object(
            discovery.socket, "socket", side_effect=OSError("blocked")
        ):
            self.assertEqual(discovery.wsd_discover(0.1), [])


class DiscoverTests(unittest.TestCase):
    def test_merges_broadcast_unicast_and_wsd_results(self):
        broadcast = [
            DiscoveredPrinter(
                "192.168.0.220", model="MA2000w", sources=["snmp-broadcast"]
            )
        ]
        unicast = [
            DiscoveredPrinter(
                "192.168.0.220",
                model="MA2000w",
                serial="S",
                firmware="F",
                sources=["snmp-unicast"],
            ),
            DiscoveredPrinter(
                "192.168.0.50", model="MA2000w", sources=["snmp-unicast"]
            ),
        ]
        wsd = [
            DiscoveredPrinter(
                "192.168.0.220",
                sources=["wsd"],
                endpoint="urn:uuid:test",
                xaddrs=["http://192.168.0.220:5357/"],
            )
        ]
        with mock.patch.object(
            discovery, "probe_snmp_broadcast", return_value=broadcast
        ), mock.patch.object(
            discovery, "probe_snmp_hosts", return_value=unicast
        ) as hosts, mock.patch.object(
            discovery, "wsd_discover", return_value=wsd
        ), mock.patch.object(
            discovery, "arp_candidates", return_value=[]
        ):
            printers = discovery.discover(timeout=0.1)

        self.assertEqual(
            [printer.address for printer in printers],
            ["192.168.0.50", "192.168.0.220"],
        )
        main = printers[1]
        self.assertEqual(main.serial, "S")
        self.assertEqual(
            main.sources, ["snmp-broadcast", "snmp-unicast", "wsd"]
        )
        self.assertEqual(main.endpoint, "urn:uuid:test")
        self.assertTrue(
            any(
                "192.168.0.220" in call.args[0]
                for call in hosts.call_args_list
            )
        )


class CliTests(unittest.TestCase):
    def test_discover_json_returns_zero(self):
        printer = DiscoveredPrinter(
            "192.168.0.220", model="MA2000w", sources=["snmp-broadcast"]
        )
        output = io.StringIO()
        with mock.patch.object(cli, "discover", return_value=[printer]):
            with redirect_stdout(output):
                code = cli.main(["--discover", "--json", "--discover-no-wsd"])
        self.assertEqual(code, 0)
        data = json.loads(output.getvalue())
        self.assertEqual(data[0]["model"], "MA2000w")

    def test_empty_discovery_returns_one(self):
        with mock.patch.object(cli, "discover", return_value=[]):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = cli.main(["--discover", "--discover-no-wsd"])
        self.assertEqual(code, 1)

    def test_discover_rejects_target_combination(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                cli.main(["--discover", "--host", "192.0.2.1"])
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
