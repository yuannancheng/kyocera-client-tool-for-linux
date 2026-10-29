import unittest

from kyocera_monitor import kmscn_raw


def packet(
    command: int,
    subtype: int,
    color: int,
    width: int,
    height: int,
    data: bytes,
) -> bytes:
    header = (
        bytes((command, subtype, color))
        + width.to_bytes(2, "big")
        + height.to_bytes(2, "big")
    )
    payload_length = 7 + len(data)
    return (
        payload_length.to_bytes(4, "big")
        + header
        + data
    )


class RawScanTests(unittest.TestCase):
    def test_decodes_calibration_bands_and_color_planes(self):
        parts = []
        for color in (2, 3, 4):
            parts.append(
                packet(0x8A, 0x8A, color, 2, 2, bytes((10, 10, 10, 10)))
            )
            parts.append(
                packet(
                    0x8A,
                    0x8B,
                    color,
                    2,
                    2,
                    bytes((100, 100, 100, 100)),
                )
            )
        parts.append(packet(0x82, 0x81, 2, 2, 2, bytes((10, 100, 200, 50))))
        parts.append(packet(0x82, 0x81, 3, 2, 2, bytes((10, 100, 200, 50))))
        parts.append(packet(0x82, 0x81, 4, 2, 2, bytes((10, 100, 200, 50))))
        parts.append(bytes.fromhex("0000000482820db3"))

        scan = kmscn_raw.decode_raw(b"".join(parts))

        self.assertEqual((scan.width, scan.height), (2, 2))
        self.assertEqual(
            list(scan.rgb[:6]),
            [13, 13, 13, 255, 255, 255],
        )
        self.assertEqual(len(scan.chunks), 9)

    def test_writes_standard_24_bit_bmp(self):
        scan = kmscn_raw.DecodedScan(
            width=2,
            height=1,
            rgb=bytes((255, 0, 0, 0, 255, 0)),
            chunks=(),
        )
        bmp = kmscn_raw.encode_bmp(scan)

        self.assertEqual(bmp[:2], b"BM")
        self.assertEqual(len(bmp), 54 + 8)
        self.assertEqual(bmp[54:62], b"\x00\x00\xff\x00\xff\x00\x00\x00")

    def test_truncated_chunk_is_rejected(self):
        with self.assertRaises(kmscn_raw.RawScanError):
            kmscn_raw.decode_raw(bytes.fromhex("00000020000000000000"))


if __name__ == "__main__":
    unittest.main()
