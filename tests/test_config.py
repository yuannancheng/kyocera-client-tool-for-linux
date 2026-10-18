import csv
import io
import json
import os
import threading
import time
import tty
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from kyocera_monitor import cli
from kyocera_monitor.config import (
    CONFIG,
    absolute_config_oid,
    build_config_commands,
    collect_config_snmp,
    decode_value,
    parse_config_response,
)
from kyocera_monitor.pjl import UEL
from kyocera_monitor.snmp import VarBind

ROOT = Path(__file__).resolve().parent.parent
TABLE = ROOT / "docs" / "reverse-engineering" / "data" / "clienttool-config-oids.tsv"


def kgetobj(pjl_object: str, status: int, pjl_type: int, value: str) -> str:
    return (
        f'@PJL KGETOBJ OBJ="{pjl_object}"\r\n'
        f"STATUS={status}\r\n"
        f"TYPE={pjl_type}\r\n"
        f'VALUE="{value}"\r\n'
        "\x0c"
    )


def config_response(commands) -> bytes:
    values = {
        '@PJL KGETOBJ OBJ="1.43.5.1.1.34.1"': (0, 2, "1"),
        '@PJL KGETOBJ OBJ="1.43.5.1.1.35.1"': (0, 2, "30"),
        '@PJL KGETOBJ OBJ="1.40.10.1.1.4.1"': (0, 64, "4330413830304443"),
        '@PJL KGETOBJ OBJ="1.40.26.2.1.3.1"': (0, 4, "7075626c6963"),
    }
    parts = []
    for command in commands:
        status, pjl_type, value = values.get(command, (2, 0, ""))
        pjl_object = command.split('"')[1]
        parts.append(kgetobj(pjl_object, status, pjl_type, value))
    return "".join(parts).encode("ascii")


def pty_responder(master_fd: int, response: bytes, expected_commands: int) -> None:
    received = b""
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        chunk = os.read(master_fd, 65536)
        if not chunk:
            break
        received += chunk
        if received.count(UEL) >= 2:
            os.write(master_fd, response)
            return
    raise AssertionError(
        f"PTY responder did not receive {expected_commands} commands"
    )


class ConfigTableTests(unittest.TestCase):
    def test_table_matches_packaged_extract(self):
        with TABLE.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        self.assertEqual(len(rows), 147)
        self.assertEqual(len(CONFIG), 147)
        for row, obj in zip(rows, CONFIG):
            self.assertEqual(int(row["item_id"]), obj.item_id)
            self.assertEqual(row["oid"], obj.oid)
            self.assertEqual(int(row["type_code"]), obj.type_code)
            self.assertEqual(int(row["index"]) + 1, obj.item_id)

    def test_commands_use_clienttool_pjl_spelling(self):
        commands = build_config_commands()
        self.assertEqual(len(commands), 147)
        self.assertEqual(commands[0], '@PJL KGETOBJ OBJ="1.43.5.1.1.23.1"')
        self.assertEqual(commands[-1], '@PJL KGETOBJ OBJ="1.40.42.1.1.6.1"')
        absolute = [
            command
            for command in commands
            if 'OBJ="#1.3.6.1.2.1.1.4.0"' in command
        ]
        self.assertEqual(len(absolute), 1)


class DecodeTests(unittest.TestCase):
    def test_integer_string_ipv4_and_hex(self):
        self.assertEqual(decode_value(2, "129"), (129, "integer"))
        self.assertEqual(
            decode_value(4, "48656c6c6f"), ("Hello", "string")
        )
        self.assertEqual(
            decode_value(4, "437573746f6d203100"), ("Custom 1", "string")
        )
        self.assertEqual(
            decode_value(4, "e6b58be8af95e7bd91e7bb9c5f322e3447"),
            ("测试网络_2.4G", "string"),
        )
        self.assertEqual(
            decode_value(64, "4330413830304443"),
            ("192.168.0.220", "ipv4"),
        )
        self.assertEqual(
            decode_value(64, "C0A800DC"), ("192.168.0.220", "ipv4")
        )
        self.assertEqual(decode_value(4, "00ff"), ("00ff", "hex"))
        self.assertEqual(decode_value(0, ""), (None, "empty"))

    def test_absolute_oid_expansion(self):
        self.assertEqual(
            absolute_config_oid("43.5.1.1.23.1"),
            "1.3.6.1.4.1.1347.43.5.1.1.23.1",
        )
        self.assertEqual(
            absolute_config_oid("1.3.6.1.2.1.1.4.0"),
            "1.3.6.1.2.1.1.4.0",
        )


class FakeSnmpClient:
    def __init__(self):
        self.calls: list[list[str]] = []

    def get(self, oids):
        requested = list(oids)
        self.calls.append(requested)
        values = {
            absolute_config_oid("43.5.1.1.23.1"): VarBind(
                absolute_config_oid("43.5.1.1.23.1"), 0x02, 1
            ),
            absolute_config_oid("42.5.1.1.43.1"): VarBind(
                absolute_config_oid("42.5.1.1.43.1"), 0x02, 72
            ),
            absolute_config_oid("1001.2.1.1.1.14.1"): VarBind(
                absolute_config_oid("1001.2.1.1.1.14.1"), 0x02, 0
            ),
            absolute_config_oid("40.10.1.1.4.1"): VarBind(
                absolute_config_oid("40.10.1.1.4.1"),
                0x40,
                b"\xc0\xa8\x00\xdc",
            ),
            absolute_config_oid("40.26.2.1.3.1"): VarBind(
                absolute_config_oid("40.26.2.1.3.1"), 0x04, b"public"
            ),
            absolute_config_oid("40.42.1.1.4.1"): VarBind(
                absolute_config_oid("40.42.1.1.4.1"),
                0x04,
                "测试网络_2.4G".encode(),
            ),
            absolute_config_oid("40.42.1.1.1.1"): VarBind(
                absolute_config_oid("40.42.1.1.1.1"), 0x02, 3
            ),
            absolute_config_oid("40.42.1.1.5.1"): VarBind(
                absolute_config_oid("40.42.1.1.5.1"), 0x02, 4
            ),
            absolute_config_oid("40.42.1.1.7.1"): VarBind(
                absolute_config_oid("40.42.1.1.7.1"), 0x02, -71
            ),
            absolute_config_oid("40.42.1.1.6.1"): VarBind(
                absolute_config_oid("40.42.1.1.6.1"), 0x02, 4
            ),
        }
        return [values[oid] for oid in requested if oid in values]


class SnmpConfigTests(unittest.TestCase):
    def test_snmp_reader_decodes_and_paginates(self):
        client = FakeSnmpClient()
        records = collect_config_snmp("printer", client=client, batch_size=16)
        self.assertEqual(len(records), 147)
        self.assertEqual(sum(record.get("status") == 0 for record in records), 10)
        by_id = {record["item_id"]: record for record in records}
        self.assertEqual(by_id[1]["display"], "1 min")
        self.assertEqual(by_id[4]["label"], "Power off timer")
        self.assertEqual(by_id[4]["vendor_name"], "kmOffModeTimer")
        self.assertEqual(by_id[50]["display"], "OFF")
        self.assertEqual(by_id[108]["vendor_name"], "kmFaxDeviceSpkVolumeLevel")
        self.assertIsNone(by_id[7]["vendor_name"])
        self.assertEqual(by_id[59]["value"], "192.168.0.220")
        self.assertEqual(by_id[65]["value"], "public")
        self.assertEqual(by_id[144]["value"], "测试网络_2.4G")
        self.assertEqual(by_id[142]["display"], "Connected")
        self.assertEqual(by_id[144]["label"], "Wi-Fi SSID")
        self.assertEqual(by_id[145]["display"], "WPA2 PSK (AES)")
        self.assertEqual(by_id[146]["display"], "-71 dBm")
        self.assertEqual(by_id[146]["unit"], "dBm")
        self.assertEqual(by_id[147]["label"], "Wi-Fi channel")
        self.assertTrue(all(len(batch) <= 16 for batch in client.calls))
        self.assertEqual(sum(len(batch) for batch in client.calls), 147)


class ResponseTests(unittest.TestCase):
    def test_known_rows_are_decoded_and_labelled(self):
        response = (
            kgetobj("1.43.5.1.1.34.1", 0, 2, "1")
            + kgetobj("1.43.5.1.1.35.1", 0, 2, "30")
            + kgetobj("1.43.5.1.1.23.1", 0, 2, "1")
            + kgetobj("1.42.5.1.1.43.1", 0, 2, "72")
            + kgetobj("1.1001.2.1.1.1.14.1", 0, 2, "0")
            + kgetobj("1.40.10.1.1.4.1", 0, 64, "4330413830304443")
            + kgetobj("1.40.26.2.1.3.1", 0, 4, "7075626c6963")
        )
        records = parse_config_response(response)
        by_id = {record["item_id"]: record for record in records}
        self.assertEqual(len(records), 147)
        self.assertEqual(by_id[1]["label"], "Sleep time")
        self.assertEqual(by_id[1]["display"], "1 min")
        self.assertEqual(by_id[2]["display"], "ON")
        self.assertEqual(by_id[3]["display"], "150 s")
        self.assertEqual(by_id[4]["label"], "Power off timer")
        self.assertEqual(by_id[4]["confidence"], "inferred")
        self.assertNotIn("label", by_id[5])
        self.assertEqual(by_id[50]["label"], "Quiet mode")
        self.assertEqual(by_id[50]["display"], "OFF")
        self.assertEqual(by_id[50]["confidence"], "inferred")
        self.assertEqual(by_id[59]["value"], "192.168.0.220")
        self.assertEqual(by_id[65]["value"], "public")
        self.assertEqual(by_id[65]["label"], "SNMP read community")
        self.assertEqual(by_id[59]["pjl_object"], "1.40.10.1.1.4.1")

    def test_failed_and_missing_rows_are_explicit(self):
        response = kgetobj("1.43.5.1.1.23.1", 2, 0, "")
        records = parse_config_response(response)
        by_id = {record["item_id"]: record for record in records}
        self.assertEqual(by_id[1]["status"], 2)
        self.assertIn("STATUS=2", by_id[1]["error"])
        self.assertEqual(by_id[2]["error"], "missing response")


class ConfigCliTests(unittest.TestCase):
    def test_config_cli_reads_through_device_channel(self):
        master, slave = os.openpty()
        tty.setraw(slave)
        path = os.ttyname(slave)
        commands = build_config_commands()
        thread = threading.Thread(
            target=pty_responder,
            args=(master, config_response(commands), len(commands)),
        )
        thread.start()
        try:
            output = io.StringIO()
            with redirect_stdout(output):
                code = cli.main(
                    [
                        "--device",
                        path,
                        "--config",
                        "--json",
                        "--timeout",
                        "3",
                        "--idle",
                        "0.2",
                    ]
                )
        finally:
            os.close(slave)
            os.close(master)
            thread.join(3)
        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["total"], 147)
        self.assertEqual(payload["read"], 4)
        by_id = {record["item_id"]: record for record in payload["objects"]}
        self.assertEqual(by_id[2]["display"], "ON")
        self.assertEqual(by_id[59]["value"], "192.168.0.220")

    def test_config_snmp_cli_renders_records_without_pjl_object(self):
        records = [
            {
                "item_id": 1,
                "oid": "43.5.1.1.23.1",
                "absolute_oid": "1.3.6.1.4.1.1347.43.5.1.1.23.1",
                "source": "snmp",
                "status": 0,
                "label": "Sleep time",
                "value": 1,
                "display": "1 min",
            }
        ]
        output = io.StringIO()
        with patch.object(cli, "collect_config_snmp", return_value=records):
            with redirect_stdout(output):
                code = cli.main(["--host", "printer", "--config", "--snmp"])
        self.assertEqual(code, 0)
        self.assertIn("Sleep time", output.getvalue())

    def test_config_snmp_cli_falls_back_to_vendor_name(self):
        records = [
            {
                "item_id": 4,
                "oid": "42.5.1.1.43.1",
                "absolute_oid": "1.3.6.1.4.1.1347.42.5.1.1.43.1",
                "source": "snmp",
                "status": 0,
                "vendor_name": "kmOffModeTimer",
                "value": 72,
                "display": 72,
            }
        ]
        output = io.StringIO()
        with patch.object(cli, "collect_config_snmp", return_value=records):
            with redirect_stdout(output):
                code = cli.main(["--host", "printer", "--config", "--snmp"])
        self.assertEqual(code, 0)
        self.assertIn("kmOffModeTimer", output.getvalue())


if __name__ == "__main__":
    unittest.main()
