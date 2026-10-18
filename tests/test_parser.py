import unittest

from kyocera_monitor.parser import NORMAL_STATUS_CODES, parse_response
from kyocera_monitor.pjl import UEL, build_request, response_complete

FIXTURE = """@PJL INFO CONFIG
IN TRAYS [2 TABLE]
\tINTRAY\tNAME\tPAPER SIZE\tMEDIA TYPE\tMAX CAPACITY
\tINTRAY1\tSingle Bypass\tA4\tPLAIN\t1
\tINTRAY2\tMain Tray\tA4\tPLAIN\t250
OUT TRAYS [1 ENUMERATED]
\tUPPER
USTATUS [4 ENUMERATED]
\tDEVICE
\tJOB
\tPAGE
\tTIMED
SERIAL NUMBER="REDACTED"
FIRMWARE DATECODE=2022.08.22 2YW_2000.001.101
\f@PJL INFO KCONFIG
BLACK TONER LEVEL=80%
BLACK COVERAGE=6.17%
ENGINE VERSION=2Y8_1000.001.302
\f@PJL INFO KNETWORKSTATUS
NETWORK INFORMATION [2 TABLE]
\tINTERFACE\tIP ADDRESS\tGATEWAY\tSUBNET MASK\tMAC ADDRESS
\tNET\t192.168.0.220\t192.168.0.1\t255.255.255.0\t00:17:C8:XX:XX:XX
\f@PJL INQUIRE TIMEOUT
300
\f@PJL INFO KUNITNAME
"?"
\f@PJL INFO KINTRAYSTATUS
IN TRAY STATUS [3 TABLE]
\tINTRAY\tSTATUS\tSIZE\tTYPE\tREMAIN
\tINTRAY1\tOK\tA4\tPLAIN\tUNKNOWN
\tINTRAY2\tOK\tA4\tPLAIN\tUNKNOWN
\f@PJL INFO STATUS
CODE=35078
DISPLAY="Sleeping...
 "
ONLINE=TRUE
\f@PJL KGETOBJ OBJ="1.42.5.1.1.16.1"
STATUS=2
TYPE=0
VALUE=""
\f@PJL KGETOBJ OBJ="2.5.1.1.10.1"
STATUS=0
TYPE=2
VALUE=1
\f"""


class ParserTests(unittest.TestCase):
    def test_ma2000w_fixture(self):
        snapshot = parse_response(FIXTURE)
        self.assertEqual(snapshot.model, None)
        self.assertEqual(snapshot.serial, "REDACTED")
        self.assertEqual(snapshot.status_code, 35078)
        self.assertEqual(snapshot.display, "Sleeping...")
        self.assertTrue(snapshot.online)
        self.assertTrue(snapshot.normal)
        self.assertEqual(snapshot.toner_level, 80)
        self.assertEqual(snapshot.coverage, 6.17)
        self.assertEqual(snapshot.network["ip"], "192.168.0.220")
        self.assertEqual(snapshot.network["mac"], "00:17:C8:XX:XX:XX")
        self.assertEqual(len(snapshot.input_trays), 2)
        self.assertEqual(snapshot.input_trays[1].capacity, "250")
        self.assertEqual(len(snapshot.tray_status), 2)
        self.assertEqual(snapshot.tray_status[0].status, "OK")
        self.assertEqual(snapshot.kgetobj["2.5.1.1.10.1"]["VALUE"], "1")
        console_localization = snapshot.kgetobj_known["console_localization"]
        self.assertEqual(console_localization["value"], 1)
        self.assertEqual(console_localization["confidence"], "verified")
        self.assertNotIn("panel_firmware_version", snapshot.kgetobj_known)

    def test_info_id(self):
        snapshot = parse_response('@PJL INFO ID\r\n"MA2000w"\r\n\f')
        self.assertEqual(snapshot.model, "MA2000w")

    def test_known_kgetobj_fields(self):
        raw = """@PJL KGETOBJ OBJ="1.46.10.1.1.5.3"
STATUS=0
TYPE=2
VALUE=3
\f@PJL KGETOBJ OBJ="1.43.10.1.1.8.1.1"
STATUS=0
TYPE=2
VALUE=129
\f@PJL KGETOBJ OBJ="1.43.10.1.1.14.1.1"
STATUS=0
TYPE=2
VALUE=10000
\f@PJL KGETOBJ OBJ="2.10.2.1.4.1.1"
STATUS=0
TYPE=2
VALUE=129
\f"""
        snapshot = parse_response(raw)
        self.assertEqual(snapshot.kgetobj_known["scan_count"]["value"], 3)
        self.assertEqual(snapshot.kgetobj_known["drum_counter"]["value"], 129)
        self.assertEqual(snapshot.kgetobj_known["drum_counter_max"]["value"], 10000)
        lifetime = snapshot.kgetobj_known["lifetime_counter"]
        self.assertEqual(lifetime["value"], 129)
        self.assertEqual(lifetime["unit"], "pages")
        self.assertEqual(lifetime["confidence"], "verified")
        self.assertEqual(
            snapshot.kgetobj["1.43.10.1.1.8.1.1"]["VALUE"], "129"
        )

    def test_known_kgetobj_ignores_unsupported_status(self):
        raw = """@PJL KGETOBJ OBJ="1.43.10.1.1.8.1.1"
STATUS=2
TYPE=0
VALUE=""
\f"""
        snapshot = parse_response(raw)
        self.assertNotIn("drum_counter", snapshot.kgetobj_known)

    def test_known_kgetobj_settings(self):
        raw = """@PJL KGETOBJ OBJ="1.43.5.1.1.22.1"
STATUS=0
TYPE=2
VALUE=60
\f@PJL KGETOBJ OBJ="1.43.5.1.1.33.1"
STATUS=0
TYPE=2
VALUE=1
\f@PJL KGETOBJ OBJ="1.43.5.1.1.34.1"
STATUS=0
TYPE=2
VALUE=0
\f@PJL KGETOBJ OBJ="1.43.5.1.1.35.1"
STATUS=0
TYPE=2
VALUE=6
\f"""
        snapshot = parse_response(raw)
        self.assertEqual(
            snapshot.kgetobj_known["form_feed_timeout"]["value"], 300
        )
        self.assertEqual(snapshot.kgetobj_known["form_feed_timeout"]["unit"], "s")
        self.assertEqual(snapshot.kgetobj_known["sleep_mode"]["value"], "ON")
        self.assertEqual(
            snapshot.kgetobj_known["auto_error_clear"]["value"], "OFF"
        )
        self.assertEqual(
            snapshot.kgetobj_known["auto_error_clear_timeout"]["value"], 30
        )
        self.assertEqual(
            snapshot.kgetobj["1.43.5.1.1.35.1"]["VALUE"], "6"
        )

    def test_warning_code(self):
        snapshot = parse_response("@PJL INFO STATUS\r\nCODE=40038\r\nONLINE=TRUE\r\n\f")
        self.assertFalse(snapshot.normal)
        self.assertTrue(snapshot.toner_alert)

    def test_normal_codes_match_original_monitor(self):
        self.assertEqual(
            NORMAL_STATUS_CODES,
            frozenset({10001, 10002, 30014, 35078, 38001, 10036, 30001}),
        )

    def test_pjl_framing(self):
        request = build_request(["@PJL INFO ID"])
        self.assertTrue(request.startswith(UEL + b"\r\n"))
        self.assertTrue(request.endswith(UEL + b"\r\n"))
        self.assertIn(b"@PJL INFO ID\r\n", request)

    def test_response_completeness(self):
        partial = b"@PJL INFO ID\r\n\"MA2000w\"\r\n"
        full = partial + b"\x0c@PJL INFO STATUS\r\nCODE=35078\r\n"
        expected = ["@PJL INFO ID", "@PJL INFO STATUS"]
        self.assertFalse(response_complete(partial, expected))
        self.assertTrue(response_complete(full, expected))


if __name__ == "__main__":
    unittest.main()
