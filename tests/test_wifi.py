import re
import unittest

from kyocera_monitor.wifi import (
    AP_BSSID,
    AP_RSSI,
    AP_SECURITY,
    AP_SSID,
    AP_TOTAL,
    SET_AP_BSSID,
    SET_AP_PSK,
    SET_AP_RESULT,
    SET_AP_SECURITY,
    SET_AP_SSID,
    SET_AP_WEP_INDEX,
    SET_AP_WEP_KEY,
    WIFI_CHANNEL,
    WIFI_CONNECTION_STATE,
    WIFI_ENABLE_STATE,
    WIFI_RSSI,
    WIFI_SECURITY,
    WIFI_SSID,
    connect_access_point,
    read_wifi_status,
    scan_access_points,
)


def hex_text(value: str) -> str:
    return value.encode("utf-8").hex().upper()


class FakeWifiChannel:
    def __init__(self, gets=None, sets=None):
        self.gets = dict(gets or {})
        self.sets = dict(sets or {})
        self.requests = []
        self.get_sequences = {}

    def send(self, data):
        text = data.decode("ascii")
        self.requests.append(text)
        match = re.search(r'@PJL K(?:GET|SET)OBJ OBJ="([^"]+)"', text)
        assert match, text
        self.oid = match.group(1)
        self.setting = "@PJL KSETOBJ" in text

    def drain(self):
        pass

    def receive(self, timeout, idle, expected=()):
        if self.setting:
            status = self.sets.get(self.oid, 0)
            return (
                f'@PJL KSETOBJ OBJ="{self.oid}"\r\n'
                f"STATUS={status}\r\n\x0c"
            ).encode()
        index = self.get_sequences.get(self.oid, 0)
        self.get_sequences[self.oid] = index + 1
        values = self.gets[self.oid]
        value = values[min(index, len(values) - 1)]
        return (
            f'@PJL KGETOBJ OBJ="{self.oid}"\r\n'
            "STATUS=0\r\nTYPE=2\r\n"
            f'VALUE="{value}"\r\n\x0c'
        ).encode()

    def close(self):
        pass


class WifiProtocolTests(unittest.TestCase):
    def test_read_status(self):
        channel = FakeWifiChannel(
            gets={
                "1." + WIFI_CONNECTION_STATE: ["3"],
                "1." + WIFI_ENABLE_STATE: ["2"],
                "1." + WIFI_SSID: [hex_text("Office")],
                "1." + WIFI_SECURITY: ["4"],
                "1." + WIFI_CHANNEL: ["6"],
                "1." + WIFI_RSSI: ["-58"],
            }
        )
        status = read_wifi_status(channel, timeout=1, idle=0.01)
        self.assertTrue(status["connected"])
        self.assertEqual(status["ssid"], "Office")
        self.assertEqual(status["security_name"], "WPA2 PSK (AES)")
        self.assertEqual(status["rssi"], -58)
        self.assertEqual(status["channel"], 6)

    def test_scan_uses_official_trigger_and_returns_hex_ssid(self):
        channel = FakeWifiChannel(
            gets={
                "1." + AP_TOTAL: ["-1", "1"],
                "1." + f"{AP_SSID}.1": [hex_text("Office")],
                "1." + f"{AP_SECURITY}.1": ["4"],
                "1." + f"{AP_BSSID}.1": ["AA:BB:CC:DD:EE:FF"],
                "1." + f"{AP_RSSI}.1": ["-44"],
            }
        )
        points = scan_access_points(
            channel,
            timeout=1,
            idle=0.01,
            scan_timeout=1,
            poll_interval=0,
        )
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0].ssid, "Office")
        self.assertEqual(points[0].security_name, "WPA2 PSK (AES)")
        self.assertIn(
            f'@PJL KSETOBJ OBJ="1.{AP_TOTAL}" VALUE =1',
            channel.requests[0],
        )

    def test_connect_sets_fields_in_official_order_and_never_logs_secret(self):
        channel = FakeWifiChannel(
            gets={
                "1." + SET_AP_RESULT: ["0"],
                "1." + WIFI_CONNECTION_STATE: ["3"],
            }
        )
        progress = []
        result = connect_access_point(
            channel,
            ssid="Office",
            security=4,
            password="correct horse battery staple",
            bssid="AA:BB:CC:DD:EE:FF",
            timeout=1,
            idle=0.01,
            connect_timeout=1,
            poll_interval=0,
            on_progress=progress.append,
        )
        self.assertTrue(result["connected"])
        self.assertEqual(
            progress,
            [
                f"writing {SET_AP_SSID}",
                f"writing {SET_AP_SECURITY}",
                f"writing {SET_AP_BSSID}",
                f"writing {SET_AP_WEP_INDEX}",
                f"writing {SET_AP_WEP_KEY}",
                f"writing {SET_AP_PSK}",
            ],
        )
        self.assertNotIn("correct horse", "\n".join(progress))
        self.assertIn(
            f'OBJ="1.{SET_AP_SSID}" VALUE ="{hex_text("Office")}"',
            channel.requests[0],
        )
        self.assertIn(f'OBJ="1.{SET_AP_PSK}"', channel.requests[5])


if __name__ == "__main__":
    unittest.main()
