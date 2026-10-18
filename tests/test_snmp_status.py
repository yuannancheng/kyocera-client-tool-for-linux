import unittest
from unittest import mock

from kyocera_monitor import snmp_status
from kyocera_monitor.snmp import VarBind


def vb(oid: str, value: object, tag: int | None = None) -> VarBind:
    if tag is not None:
        return VarBind(oid, tag, value)
    if isinstance(value, bytes):
        tag = 0x04
    elif isinstance(value, int):
        tag = 0x02
    else:
        tag = 0x05
    return VarBind(oid, tag, value)


class FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, oids):
        values = {
            snmp_status.SCALAR_OIDS["sys_descr"]: "KYOCERA Document Solutions Printing System",
            snmp_status.SCALAR_OIDS["sys_uptime"]: 2207587,
            snmp_status.SCALAR_OIDS["sys_name"]: b"TESTHOST",
            snmp_status.SCALAR_OIDS["device_status"]: 2,
            snmp_status.SCALAR_OIDS["printer_status"]: 3,
            snmp_status.SCALAR_OIDS["model"]: "MA2000w",
            snmp_status.SCALAR_OIDS["base_model"]: "MA2000w",
            snmp_status.SCALAR_OIDS["serial"]: "REDACTED",
            snmp_status.SCALAR_OIDS["firmware"]: "2YW_2000.001.101",
            snmp_status.SCALAR_OIDS["ip"]: bytes([192, 168, 0, 220]),
            snmp_status.SCALAR_OIDS["subnet"]: bytes([255, 255, 255, 0]),
            snmp_status.SCALAR_OIDS["gateway"]: bytes([192, 168, 0, 1]),
            snmp_status.SCALAR_OIDS["mac"]: bytes.fromhex("021122334455"),
            snmp_status.SCALAR_OIDS["page_count"]: 53,
            snmp_status.SCALAR_OIDS["scan_count"]: 3,
            snmp_status.SCALAR_OIDS["device_uptime"]: 24958,
            snmp_status.SCALAR_OIDS["sleep_mode"]: 1,
            snmp_status.SCALAR_OIDS["auto_error_clear"]: 0,
            snmp_status.SCALAR_OIDS["auto_error_clear_timeout"]: 6,
            snmp_status.SCALAR_OIDS["form_feed_timeout"]: 60,
        }
        ip_oids = {
            snmp_status.SCALAR_OIDS["ip"],
            snmp_status.SCALAR_OIDS["subnet"],
            snmp_status.SCALAR_OIDS["gateway"],
        }
        return [
            vb(oid, value, 0x40 if oid in ip_oids else None)
            for oid, value in values.items()
            if oid in oids
        ]

    def walk(self, root, max_rows=200):
        tables = {
            snmp_status.SUPPLIES: [
                vb("1.3.6.1.2.1.43.11.1.1.4.1.1", 3),
                vb("1.3.6.1.2.1.43.11.1.1.5.1.1", 3),
                vb("1.3.6.1.2.1.43.11.1.1.6.1.1", b"TK"),
                vb("1.3.6.1.2.1.43.11.1.1.7.1.1", 7),
                vb("1.3.6.1.2.1.43.11.1.1.8.1.1", 700),
                vb("1.3.6.1.2.1.43.11.1.1.9.1.1", 560),
            ],
            snmp_status.INPUTS: [
                vb("1.3.6.1.2.1.43.8.2.1.9.1.1", 150),
                vb("1.3.6.1.2.1.43.8.2.1.10.1.1", -2),
                vb("1.3.6.1.2.1.43.8.2.1.11.1.1", 4),
                vb("1.3.6.1.2.1.43.8.2.1.12.1.1", b"PLAIN"),
                vb("1.3.6.1.2.1.43.8.2.1.15.1.1", b"Cassette 1"),
                vb("1.3.6.1.2.1.43.8.2.1.18.1.1", b"Cassette 1"),
            ],
            snmp_status.ALERTS: [
                vb("1.3.6.1.2.1.43.18.1.1.2.1.1", 5),
                vb("1.3.6.1.2.1.43.18.1.1.3.1.1", 3),
                vb("1.3.6.1.2.1.43.18.1.1.4.1.1", 10),
                vb("1.3.6.1.2.1.43.18.1.1.5.1.1", 1),
                vb("1.3.6.1.2.1.43.18.1.1.6.1.1", 0),
                vb("1.3.6.1.2.1.43.18.1.1.7.1.1", 1001),
                vb("1.3.6.1.2.1.43.18.1.1.8.1.1", b""),
                vb("1.3.6.1.2.1.43.18.1.1.9.1.1", 8040),
            ],
            snmp_status.CONSOLE: [
                vb(
                    "1.3.6.1.2.1.43.16.5.1.2.1.1",
                    b"Sleeping...\r\n \x00\x00\x00",
                )
            ],
        }
        return [item for item in tables.get(root, [])][:max_rows]

    def walk_columns(self, root, columns, max_rows=200):
        prefix_length = len(root) + 1
        wanted = {str(column) for column in columns}
        return [
            item
            for item in self.walk(root, max_rows)
            if item.oid[prefix_length:].split(".", 1)[0] in wanted
        ]

    def walk_rows(self, root, columns, *, sentinel_column, max_rows=200):
        return self.walk_columns(root, columns, max_rows)


class SnmpStatusTests(unittest.TestCase):
    def collect(self):
        with mock.patch.object(snmp_status, "SnmpClient", FakeClient):
            return snmp_status.collect_snmp_snapshot("192.0.2.1")

    def test_page_count_uses_full_marker_instance(self):
        self.assertEqual(
            snmp_status.SCALAR_OIDS["page_count"],
            "1.3.6.1.2.1.43.10.2.1.4.1.1",
        )

    def test_scalar_and_network_mapping(self):
        snapshot = self.collect()
        self.assertEqual(snapshot.model, "MA2000w")
        self.assertEqual(snapshot.serial, "REDACTED")
        self.assertEqual(snapshot.firmware, "2YW_2000.001.101")
        self.assertEqual(snapshot.network["ip"], "192.168.0.220")
        self.assertEqual(snapshot.network["mac"], "02:11:22:33:44:55")
        self.assertEqual(snapshot.snmp["page_count"], 53)
        self.assertEqual(snapshot.snmp["scan_count"], 3)
        self.assertEqual(snapshot.snmp["device_uptime_seconds"], 24958)
        self.assertEqual(snapshot.snmp["sleep_mode"], "ON")
        self.assertEqual(snapshot.snmp["auto_error_clear"], "OFF")
        self.assertEqual(snapshot.snmp["auto_error_clear_timeout_seconds"], 30)
        self.assertEqual(snapshot.snmp["form_feed_timeout_seconds"], 300)
        self.assertEqual(snapshot.timeout, 300)
        self.assertEqual(snapshot.snmp["printer_status_name"], "idle")
        self.assertTrue(snapshot.normal)

    def test_supply_and_console_mapping(self):
        snapshot = self.collect()
        self.assertEqual(snapshot.toner_level, 80)
        self.assertEqual(snapshot.display, "Sleeping...")
        self.assertEqual(snapshot.snmp["supplies"][0]["max_capacity"], 700)
        self.assertEqual(snapshot.snmp["supplies"][0]["percent"], 80)

    def test_input_and_alert_mapping(self):
        snapshot = self.collect()
        self.assertEqual(snapshot.input_trays[0].name, "Cassette 1")
        self.assertEqual(snapshot.input_trays[0].media, "PLAIN")
        self.assertEqual(snapshot.input_trays[0].remain, "UNKNOWN")
        alert = snapshot.snmp["alerts"][0]
        self.assertEqual(alert["severity"], 5)
        self.assertEqual(alert["severity_name"], "warning_binary_change_event")
        self.assertEqual(alert["training_level"], 3)
        self.assertEqual(alert["training_level_name"], "untrained")
        self.assertEqual(alert["group"], 10)
        self.assertEqual(alert["group_name"], "marker")
        self.assertEqual(alert["code"], 1001)
        self.assertEqual(alert["code_name"], "marker_fuser_under_temperature")
        self.assertEqual(snapshot.to_dict()["snmp"]["scan_count"], 3)


if __name__ == "__main__":
    unittest.main()
