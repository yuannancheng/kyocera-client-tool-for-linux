import csv
import copy
import io
import json
import os
import stat
import tempfile
import threading
import time
import tty
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
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
from kyocera_monitor.config_snapshot import (
    ConfigSnapshotError,
    build_config_snapshot,
    compare_config_snapshots,
    load_config_snapshot,
    save_config_snapshot,
)
from kyocera_monitor.config_write_plan import (
    ConfigWritePlanError,
    build_config_write_plan,
    parse_config_assignment,
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


class ConfigSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.records = parse_config_response(
            kgetobj("1.43.5.1.1.34.1", 0, 2, "1")
            + kgetobj("1.40.10.1.1.4.1", 0, 64, "4330413830304443")
        )
        self.snapshot = build_config_snapshot(
            self.records,
            transport="pjl",
            target="/dev/usb/lp0",
        )

    def test_snapshot_is_complete_and_integrity_checked(self):
        self.assertEqual(self.snapshot["total"], 147)
        self.assertEqual(self.snapshot["read"], 2)
        self.assertEqual(len(self.snapshot["checksum"]["canonical_json"]), 64)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "baseline.json"
            saved = save_config_snapshot(path, self.snapshot)
            self.assertEqual(saved, path)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            loaded = load_config_snapshot(path)
            self.assertEqual(loaded, self.snapshot)

    def test_snapshot_rejects_overwrite_and_insecure_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "baseline.json"
            save_config_snapshot(path, self.snapshot)
            with self.assertRaises(ConfigSnapshotError):
                save_config_snapshot(path, self.snapshot)
            path.chmod(0o644)
            with self.assertRaises(ConfigSnapshotError):
                load_config_snapshot(path)
            loaded = load_config_snapshot(path, require_private=False)
            self.assertEqual(loaded, self.snapshot)

    def test_snapshot_detects_tampering(self):
        tampered = copy.deepcopy(self.snapshot)
        tampered["objects"][1]["value"] = "0"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tampered.json"
            path.write_text(json.dumps(tampered), encoding="utf-8")
            path.chmod(0o600)
            with self.assertRaisesRegex(ConfigSnapshotError, "checksum"):
                load_config_snapshot(path)

    def test_compare_reports_semantic_changes_and_binds_transport_target(self):
        changed_records = copy.deepcopy(self.records)
        changed_records[1]["value"] = 0
        changed_records[1]["display"] = "OFF"
        current = build_config_snapshot(
            changed_records,
            transport="pjl",
            target="/dev/usb/lp0",
        )
        result = compare_config_snapshots(self.snapshot, current)
        self.assertEqual(result["changed"], 1)
        self.assertEqual(result["volatile_changed"], 0)
        self.assertEqual(result["read_status_changed"], 0)
        self.assertEqual(result["changes"][0]["item_id"], 2)
        self.assertEqual(result["changes"][0]["before"]["display"], "ON")
        self.assertEqual(result["changes"][0]["after"]["display"], "OFF")

        other_transport = build_config_snapshot(
            changed_records,
            transport="snmp",
            target="/dev/usb/lp0",
        )
        with self.assertRaisesRegex(ConfigSnapshotError, "transports"):
            compare_config_snapshots(self.snapshot, other_transport)
        other_target = build_config_snapshot(
            changed_records,
            transport="pjl",
            target="/dev/usb/lp1",
        )
        with self.assertRaisesRegex(ConfigSnapshotError, "target"):
            compare_config_snapshots(self.snapshot, other_target)
        mismatched = compare_config_snapshots(
            self.snapshot,
            other_target,
            allow_target_mismatch=True,
        )
        self.assertFalse(mismatched["target_matches"])

    def test_compare_separates_value_changes_from_read_failures(self):
        missing_records = copy.deepcopy(self.records)
        missing_records[1]["status"] = 2
        missing_records[1]["value"] = None
        missing_records[1]["display"] = None
        missing_records[1]["error"] = "STATUS=2"
        current = build_config_snapshot(
            missing_records,
            transport="pjl",
            target="/dev/usb/lp0",
        )
        result = compare_config_snapshots(self.snapshot, current)
        self.assertEqual(result["changed"], 0)
        self.assertEqual(result["volatile_changed"], 0)
        self.assertEqual(result["read_status_changed"], 1)
        self.assertEqual(result["read_status_changes"][0]["item_id"], 2)
        self.assertEqual(result["unchanged"], 146)

    def test_read_only_telemetry_does_not_count_as_a_config_change(self):
        rssi_records = copy.deepcopy(self.records)
        rssi_index = next(
            index
            for index, record in enumerate(rssi_records)
            if record["item_id"] == 146
        )
        rssi_records[rssi_index]["status"] = 0
        rssi_records[rssi_index]["value"] = -69
        rssi_records[rssi_index]["display"] = "-69 dBm"
        baseline = build_config_snapshot(
            rssi_records,
            transport="pjl",
            target="/dev/usb/lp0",
        )
        rssi_records[rssi_index]["value"] = -71
        rssi_records[rssi_index]["display"] = "-71 dBm"
        current = build_config_snapshot(
            rssi_records,
            transport="pjl",
            target="/dev/usb/lp0",
        )
        result = compare_config_snapshots(baseline, current)
        self.assertEqual(result["changed"], 0)
        self.assertEqual(result["volatile_changed"], 1)
        self.assertEqual(result["read_status_changed"], 0)
        self.assertEqual(result["volatile_changes"][0]["item_id"], 146)

    def test_config_cli_saves_then_compares_snmp_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "baseline.json"
            output = io.StringIO()
            with patch.object(cli, "collect_config_snmp", return_value=self.records):
                with redirect_stdout(output):
                    code = cli.main(
                        [
                            "--host",
                            "printer",
                            "--config",
                            "--snmp",
                            "--config-save",
                            str(path),
                        ]
                    )
            self.assertEqual(code, 0)
            self.assertTrue(path.is_file())

            changed = copy.deepcopy(self.records)
            changed[1]["value"] = 0
            changed[1]["display"] = "OFF"
            output = io.StringIO()
            with patch.object(cli, "collect_config_snmp", return_value=changed):
                with redirect_stdout(output):
                    code = cli.main(
                        [
                            "--host",
                            "printer",
                            "--config",
                            "--snmp",
                            "--config-compare",
                            str(path),
                            "--json",
                        ]
                    )
            self.assertEqual(code, 1)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["comparison"]["changed"], 1)
            self.assertEqual(payload["baseline"]["target"], "printer")


class ConfigWritePlanTests(unittest.TestCase):
    def setUp(self):
        self.records = parse_config_response(
            kgetobj("1.43.5.1.1.34.1", 0, 2, "1")
            + kgetobj("1.40.10.1.1.4.1", 0, 64, "4330413830304443")
        )
        self.baseline = build_config_snapshot(
            self.records,
            transport="snmp",
            target="printer",
        )

    def test_assignment_parser_is_strict(self):
        self.assertEqual(parse_config_assignment("2=OFF"), (2, "OFF"))
        self.assertEqual(parse_config_assignment(" 2 = 0 "), (2, "0"))
        for text in ("2", "2=0=1", "a=1", "2=ON extra"):
            with self.assertRaises(ConfigWritePlanError):
                parse_config_assignment(text)

    def test_plan_contains_preview_rollback_and_disabled_execution(self):
        current = build_config_snapshot(
            copy.deepcopy(self.records),
            transport="snmp",
            target="printer",
        )
        plan = build_config_write_plan(
            self.baseline,
            current,
            "2=OFF",
            created_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
        )
        self.assertTrue(plan["review"]["ready_for_executor_implementation"])
        self.assertFalse(plan["execution"]["allowed"])
        self.assertEqual(plan["object"]["item_id"], 2)
        self.assertEqual(plan["object"]["absolute_oid"], "1.3.6.1.4.1.1347.43.5.1.1.34.1")
        self.assertEqual(plan["before"]["value"], 1)
        self.assertEqual(plan["requested"]["value"], 0)
        self.assertEqual(plan["rollback"]["value"], 1)
        self.assertEqual(
            plan["commands"]["pjl_line"],
            '@PJL KSETOBJ OBJ="1.43.5.1.1.34.1" VALUE =0',
        )
        self.assertEqual(
            plan["commands"]["pjl_rollback_line"],
            '@PJL KSETOBJ OBJ="1.43.5.1.1.34.1" VALUE =1',
        )
        self.assertEqual(plan["commands"]["snmp_set"]["syntax"], "Integer")
        self.assertEqual(len(plan["confirmation"]["token"]), 64)

    def test_plan_blocks_drift_read_failures_and_noop(self):
        drifted_records = copy.deepcopy(self.records)
        drifted_records[1]["value"] = 0
        drifted_records[1]["display"] = "OFF"
        drifted = build_config_snapshot(
            drifted_records,
            transport="snmp",
            target="printer",
        )
        plan = build_config_write_plan(self.baseline, drifted, "2=OFF")
        self.assertIn(
            "unexpected_configuration_drift",
            plan["review"]["blockers"],
        )
        self.assertIn(
            "requested_value_equals_current_value",
            plan["review"]["blockers"],
        )

        missing_records = copy.deepcopy(self.records)
        missing_records[1]["status"] = 2
        missing_records[1]["value"] = None
        missing_records[1]["display"] = None
        missing = build_config_snapshot(
            missing_records,
            transport="snmp",
            target="printer",
        )
        plan = build_config_write_plan(self.baseline, missing, "2=OFF")
        self.assertIn("current_object_not_readable", plan["review"]["blockers"])
        self.assertIn("unstable_configuration_read", plan["review"]["blockers"])

        missing_baseline = build_config_snapshot(
            missing_records,
            transport="snmp",
            target="printer",
        )
        plan = build_config_write_plan(missing_baseline, missing_baseline, "2=OFF")
        self.assertIn("baseline_object_not_readable", plan["review"]["blockers"])
        self.assertIsNone(plan["commands"]["pjl_rollback_line"])
        self.assertIsNone(plan["commands"]["snmp_rollback"]["value"])

    def test_plan_rejects_unknown_items_and_values(self):
        current = build_config_snapshot(
            copy.deepcopy(self.records),
            transport="snmp",
            target="printer",
        )
        with self.assertRaisesRegex(ConfigWritePlanError, "not an approved"):
            build_config_write_plan(self.baseline, current, "1=2")
        with self.assertRaisesRegex(ConfigWritePlanError, "accepts only"):
            build_config_write_plan(self.baseline, current, "2=2")

    def test_cli_generates_plan_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "baseline.json"
            save_config_snapshot(path, self.baseline)
            output = io.StringIO()
            with patch.object(cli, "collect_config_snmp", return_value=self.records):
                with redirect_stdout(output):
                    code = cli.main(
                        [
                            "--host",
                            "printer",
                            "--config",
                            "--snmp",
                            "--config-plan",
                            str(path),
                            "--config-set",
                            "2=OFF",
                            "--json",
                        ]
                    )
            self.assertEqual(code, 0)
            payload = json.loads(output.getvalue())
            self.assertFalse(payload["write_plan"]["execution"]["allowed"])
            self.assertTrue(
                payload["write_plan"]["review"][
                    "ready_for_executor_implementation"
                ]
            )


if __name__ == "__main__":
    unittest.main()
