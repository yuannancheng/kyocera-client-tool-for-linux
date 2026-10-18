import unittest
from pathlib import Path

from kyocera_monitor.parser import parse_response
from kyocera_monitor.pjl import (
    QUERY_SEQUENCE,
    PjlError,
    missing_commands,
    query_merged,
    split_segments,
)

SAMPLE = Path(__file__).resolve().parents[1] / (
    "docs/reverse-engineering/samples/ma2000w-pjl.txt"
)


class FakeChannel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[bytes] = []

    def send(self, data):
        self.requests.append(data)

    def drain(self):
        pass

    def receive(self, timeout, idle, expected=()):
        if not self.responses:
            return b""
        return self.responses.pop(0)

    def close(self):
        pass


def requested_commands(request: bytes) -> list[str]:
    return [
        line.strip()
        for line in request.decode("ascii").splitlines()
        if line.startswith("@PJL ")
    ]


class SegmentTests(unittest.TestCase):
    def test_real_sample_has_every_query(self):
        raw = SAMPLE.read_bytes()
        segments = split_segments(raw)
        self.assertEqual(len(segments), 16)
        self.assertEqual(missing_commands(raw, QUERY_SEQUENCE), [])

    def test_form_feed_prefixed_echo_and_quoted_kgetobj(self):
        raw = (
            b'@PJL INFO ID\r\n"MA2000w"\r\n'
            b'\x0c@PJL KGETOBJ OBJ="1.46.10.1.1.5.3"\r\n'
            b"STATUS=0\r\nTYPE=2\r\nVALUE=3\r\n\x0c"
        )
        segments = split_segments(raw)
        self.assertEqual(
            list(segments),
            ["@PJL INFO ID", '@PJL KGETOBJ OBJ="1.46.10.1.1.5.3"'],
        )
        self.assertTrue(segments["@PJL INFO ID"].startswith(b"@PJL INFO ID"))
        self.assertNotIn(b"\x0c", segments["@PJL INFO ID"])


class PartialRetryTests(unittest.TestCase):
    def test_retries_only_missing_segments_and_merges_in_order(self):
        commands = ("@PJL INFO CONFIG", "@PJL INFO ID", "@PJL INFO STATUS")
        channel = FakeChannel(
            [
                b'@PJL INFO CONFIG\r\nSERIAL NUMBER="REDACTED"\r\n',
                b'@PJL INFO ID\r\n"MA2000w"\r\n'
                b"\x0c@PJL INFO STATUS\r\nCODE=35078\r\nONLINE=TRUE\r\n\x0c",
            ]
        )
        raw = query_merged(channel, commands, timeout=1, idle=0.05, retries=1)
        self.assertEqual(requested_commands(channel.requests[0]), list(commands))
        self.assertEqual(
            requested_commands(channel.requests[1]),
            ["@PJL INFO ID", "@PJL INFO STATUS"],
        )
        snapshot = parse_response(raw)
        self.assertEqual(snapshot.serial, "REDACTED")
        self.assertEqual(snapshot.model, "MA2000w")
        self.assertEqual(snapshot.status_code, 35078)
        self.assertLess(raw.index(b"@PJL INFO CONFIG"), raw.index(b"@PJL INFO ID"))

    def test_retry_stops_after_requested_rounds(self):
        commands = ("@PJL INFO ID", "@PJL INFO STATUS")
        channel = FakeChannel(
            [
                b'@PJL INFO ID\r\n"MA2000w"\r\n',
                b'@PJL INFO ID\r\n"MA2000w"\r\n',
            ]
        )
        raw = query_merged(channel, commands, timeout=1, idle=0.05, retries=1)
        snapshot = parse_response(raw)
        self.assertEqual(snapshot.model, "MA2000w")
        self.assertIsNone(snapshot.status_code)
        self.assertEqual(len(channel.requests), 2)
        self.assertEqual(
            requested_commands(channel.requests[1]), ["@PJL INFO STATUS"]
        )

    def test_empty_response_raises(self):
        channel = FakeChannel([b"", b""])
        with self.assertRaises(PjlError):
            query_merged(
                channel,
                ("@PJL INFO ID",),
                timeout=1,
                idle=0.05,
                retries=1,
            )

    def test_unrecognized_response_is_returned_unchanged(self):
        payload = b'"MA2000w"\r\nCODE=35078\r\n'
        channel = FakeChannel([payload])
        raw = query_merged(channel, ("@PJL INFO ID",), timeout=1, retries=0)
        self.assertEqual(raw, payload)


if __name__ == "__main__":
    unittest.main()
