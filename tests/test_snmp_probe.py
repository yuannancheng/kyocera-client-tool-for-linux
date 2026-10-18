import unittest
from unittest import mock

from kyocera_monitor import snmp as snmp_probe


def _response(
    varbinds: list[snmp_probe.VarBind],
    *,
    error_status: int = 0,
    error_index: int = 0,
) -> bytes:
    encoded = b"".join(
        snmp_probe.encode_tlv(
            0x30,
            snmp_probe.encode_oid(varbind.oid)
            + snmp_probe.encode_tlv(0x05, b""),
        )
        for varbind in varbinds
    )
    pdu = snmp_probe.encode_tlv(
        0xA2,
        snmp_probe.encode_integer(1)
        + snmp_probe.encode_integer(error_status)
        + snmp_probe.encode_integer(error_index)
        + snmp_probe.encode_tlv(0x30, encoded),
    )
    return snmp_probe.encode_tlv(
        0x30,
        snmp_probe.encode_integer(0)
        + snmp_probe.encode_tlv(0x04, b"public")
        + pdu,
    )


class WalkTests(unittest.TestCase):
    def test_walk_stops_when_leaving_requested_subtree(self):
        responses = [
            _response(
                [
                    snmp_probe.VarBind("1.3.6.1.2.1.1.1.0", 0x04, b"descr"),
                    snmp_probe.VarBind("1.3.6.1.2.1.2.1.0", 0x02, 1),
                ]
            )
        ]
        with mock.patch.object(snmp_probe, "exchange", side_effect=responses) as sent:
            rows = snmp_probe.walk(
                "192.0.2.1", 161, "public", 0, "1.3.6.1.2.1.1", 1, 0, 20, False
            )
        self.assertEqual([row.oid for row in rows], ["1.3.6.1.2.1.1.1.0"])
        self.assertEqual(sent.call_count, 1)

    def test_walk_pages_until_subtree_ends(self):
        responses = [
            _response([snmp_probe.VarBind("1.3.6.1.2.1.1.1.0", 0x04, b"descr")]),
            _response(
                [snmp_probe.VarBind("1.3.6.1.2.1.1.9.1.2.1", 0x04, b"other")]
            ),
            _response(
                [
                    snmp_probe.VarBind(
                        "1.3.6.1.2.1.1.9.1.2.1",
                        snmp_probe.NO_SUCH_INSTANCE,
                        "NoSuchInstance",
                    )
                ]
            ),
        ]
        with mock.patch.object(snmp_probe, "exchange", side_effect=responses):
            rows = snmp_probe.walk(
                "192.0.2.1", 161, "public", 0, "1.3.6.1.2.1.1", 1, 0, 20, False
            )
        self.assertEqual(
            [row.oid for row in rows],
            ["1.3.6.1.2.1.1.1.0", "1.3.6.1.2.1.1.9.1.2.1"],
        )

    def test_get_drops_unsupported_oid_after_v1_error(self):
        first = "1.3.6.1.2.1.1.1.0"
        missing = "1.3.6.1.2.1.43.10.2.1.4.1"
        responses = [
            _response(
                [
                    snmp_probe.VarBind(first, 0x05, None),
                    snmp_probe.VarBind(missing, 0x05, None),
                ],
                error_status=2,
                error_index=2,
            ),
            _response([snmp_probe.VarBind(first, 0x04, b"descr")]),
        ]
        client = snmp_probe.SnmpClient("192.0.2.1", version="1")
        with mock.patch.object(snmp_probe, "exchange", side_effect=responses) as sent:
            rows = client.get([first, missing])
        self.assertEqual([row.oid for row in rows], [first])
        self.assertEqual(sent.call_count, 2)


class ColumnWalkTests(unittest.TestCase):
    root = "1.3.6.1.2.1.43.11.1.1"

    def test_column_walk_advances_all_columns_in_one_request(self):
        responses = [
            _response(
                [
                    snmp_probe.VarBind(f"{self.root}.4.1.1", 0x02, 3),
                    snmp_probe.VarBind(f"{self.root}.5.1.1", 0x02, 3),
                ]
            ),
            _response(
                [
                    snmp_probe.VarBind(f"{self.root}.4.1.2", 0x02, 3),
                    snmp_probe.VarBind(f"{self.root}.5.1.2", 0x02, 7),
                ]
            ),
            _response(
                [
                    snmp_probe.VarBind(f"{self.root}.5.1.1", 0x02, 0),
                    snmp_probe.VarBind(f"{self.root}.6.1.1", 0x04, b"TK"),
                ]
            ),
        ]
        with mock.patch.object(snmp_probe, "exchange", side_effect=responses) as sent:
            rows = snmp_probe.walk_columns(
                "192.0.2.1",
                161,
                "public",
                0,
                self.root,
                (4, 5),
                1,
                0,
                20,
            )
        self.assertEqual(
            [row.oid for row in rows],
            [
                f"{self.root}.4.1.1",
                f"{self.root}.5.1.1",
                f"{self.root}.4.1.2",
                f"{self.root}.5.1.2",
            ],
        )
        self.assertEqual(sent.call_count, 3)
        self.assertIn(
            snmp_probe.encode_oid(f"{self.root}.4.1.1"),
            sent.call_args_list[1].args[2],
        )

    def test_column_walk_drops_column_rejected_by_snmpv1(self):
        responses = [
            _response(
                [
                    snmp_probe.VarBind(f"{self.root}.4.1.1", 0x05, None),
                    snmp_probe.VarBind(f"{self.root}.5.1.1", 0x05, None),
                ],
                error_status=2,
                error_index=1,
            ),
            _response(
                [snmp_probe.VarBind(f"{self.root}.5.1.1", 0x02, 3)]
            ),
            _response(
                [snmp_probe.VarBind(f"{self.root}.6.1.1", 0x04, b"TK")]
            ),
        ]
        with mock.patch.object(snmp_probe, "exchange", side_effect=responses) as sent:
            rows = snmp_probe.walk_columns(
                "192.0.2.1",
                161,
                "public",
                0,
                self.root,
                (4, 5),
                1,
                0,
                20,
            )
        self.assertEqual([row.oid for row in rows], [f"{self.root}.5.1.1"])
        self.assertEqual(sent.call_count, 3)


class RowWalkTests(unittest.TestCase):
    root = "1.3.6.1.2.1.43.11.1.1"

    def test_row_walk_enumerates_then_gets_columns(self):
        responses = [
            _response(
                [snmp_probe.VarBind(f"{self.root}.8.1.1", 0x02, 700)]
            ),
            _response(
                [snmp_probe.VarBind(f"{self.root}.9.1.1", 0x02, 560)]
            ),
            _response(
                [
                    snmp_probe.VarBind(f"{self.root}.4.1.1", 0x02, 3),
                    snmp_probe.VarBind(f"{self.root}.8.1.1", 0x02, 700),
                ]
            ),
        ]
        client = snmp_probe.SnmpClient("192.0.2.1", version="1", retries=0)
        with mock.patch.object(snmp_probe, "exchange", side_effect=responses) as sent:
            rows = client.walk_rows(
                self.root, (4, 8), sentinel_column=8, max_rows=20
            )
        self.assertEqual(
            [row.oid for row in rows],
            [f"{self.root}.4.1.1", f"{self.root}.8.1.1"],
        )
        self.assertEqual(sent.call_count, 3)
        # The last request must be a GET (0xA0), not another GETNEXT.
        self.assertIn(b"\xa0", sent.call_args_list[2].args[2])


if __name__ == "__main__":
    unittest.main()
