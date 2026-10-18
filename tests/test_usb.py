import io
import json
import os
import threading
import time
import tty
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from kyocera_monitor import cli
from kyocera_monitor.pjl import (
    QUERY_SEQUENCE,
    UEL,
    USB_QUERY_SEQUENCE,
    open_channel,
    query,
)
from kyocera_monitor.usb import (
    UsbError,
    UsbPrinter,
    discover_usb_printers,
    select_usb_printer,
)


def usb_response(commands=QUERY_SEQUENCE) -> bytes:
    parts: list[bytes] = []
    for command in commands:
        parts.append(command.encode("ascii") + b"\r\n")
        if command == "@PJL INFO ID":
            parts.append(b'"MA2000w"\r\n')
        elif command == "@PJL INFO STATUS":
            parts.append(b"CODE=35078\r\nONLINE=TRUE\r\n")
        elif command == "@PJL INFO KCONFIG":
            parts.append(b"BLACK TONER LEVEL=80%\r\n")
        else:
            parts.append(b"\r\n")
    return b"".join(parts) + b"\x0c"


def pty_responder(master_fd: int, response: bytes) -> None:
    received = b""
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        chunk = os.read(master_fd, 4096)
        if not chunk:
            break
        received += chunk
        if received.count(UEL) >= 2:
            os.write(master_fd, response)
            return
    raise AssertionError("PTY responder did not receive a complete PJL request")


def make_pty() -> tuple[int, int, str]:
    master, slave = os.openpty()
    tty.setraw(slave)
    path = os.ttyname(slave)
    return master, slave, path


class UsbDiscoveryTests(unittest.TestCase):
    def test_discovery_reads_usb_identity_from_sysfs(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            usb_device = root / "sys/devices/usb1/1-1"
            usb_device.mkdir(parents=True)
            (usb_device / "idVendor").write_text("0482\n", encoding="ascii")
            (usb_device / "idProduct").write_text("0d51\n", encoding="ascii")
            (usb_device / "manufacturer").write_text("Kyocera\n", encoding="ascii")
            (usb_device / "product").write_text("MA2000w\n", encoding="ascii")

            interface = usb_device / "1-1:1.0"
            interface.mkdir()
            (interface / "device").symlink_to(usb_device, target_is_directory=True)
            class_dir = root / "sys/class/usbmisc"
            class_dir.mkdir(parents=True)
            (class_dir / "lp0").symlink_to(interface, target_is_directory=True)

            dev_dir = root / "dev/usb"
            dev_dir.mkdir(parents=True)
            device_path = dev_dir / "lp0"
            device_path.touch()

            printers = discover_usb_printers(
                sysfs_root=root / "sys",
                device_glob=str(dev_dir / "lp*"),
            )
            self.assertEqual(len(printers), 1)
            self.assertEqual(printers[0].device, str(device_path))
            self.assertEqual(printers[0].vendor_id, 0x0482)
            self.assertEqual(printers[0].product_id, 0x0D51)
            self.assertEqual(printers[0].manufacturer, "Kyocera")
            self.assertEqual(printers[0].product, "MA2000w")

    def test_selection_prefers_ma2000w(self):
        printers = [
            UsbPrinter("/dev/usb/lp0", vendor_id=0x1234, product_id=0x0001),
            UsbPrinter("/dev/usb/lp1", vendor_id=0x0482, product_id=0x0D51),
        ]
        self.assertEqual(select_usb_printer(printers).device, "/dev/usb/lp1")

    def test_ambiguous_selection_fails(self):
        printers = [
            UsbPrinter("/dev/usb/lp0", vendor_id=0x0482, product_id=0x0493),
            UsbPrinter("/dev/usb/lp1", vendor_id=0x0482, product_id=0x0494),
        ]
        with self.assertRaises(UsbError):
            select_usb_printer(printers)


class UsbTransportTests(unittest.TestCase):
    def test_usb_query_sequence_starts_with_info_id(self):
        self.assertEqual(USB_QUERY_SEQUENCE[0], "@PJL INFO ID")
        self.assertEqual(len(USB_QUERY_SEQUENCE), 16)

    def test_device_channel_round_trip(self):
        master, slave, path = make_pty()
        response = usb_response(["@PJL INFO ID", "@PJL INFO STATUS"])
        thread = threading.Thread(target=pty_responder, args=(master, response))
        thread.start()
        try:
            with open_channel(device=path) as channel:
                raw = query(
                    channel,
                    ["@PJL INFO ID", "@PJL INFO STATUS"],
                    timeout=2,
                    idle=0.2,
                )
        finally:
            os.close(slave)
            os.close(master)
            thread.join(3)
        self.assertIn(b'"MA2000w"', raw)
        self.assertIn(b"CODE=35078", raw)

    def test_cli_device_json(self):
        master, slave, path = make_pty()
        thread = threading.Thread(target=pty_responder, args=(master, usb_response()))
        thread.start()
        try:
            output = io.StringIO()
            with redirect_stdout(output):
                code = cli.main(
                    [
                        "--device",
                        path,
                        "--json",
                        "--timeout",
                        "2",
                        "--idle",
                        "0.2",
                    ]
                )
        finally:
            os.close(slave)
            os.close(master)
            thread.join(3)
        self.assertEqual(code, 0)
        snapshot = json.loads(output.getvalue())
        self.assertEqual(snapshot["model"], "MA2000w")
        self.assertEqual(snapshot["status_code"], 35078)
        self.assertTrue(snapshot["normal"])


if __name__ == "__main__":
    unittest.main()
