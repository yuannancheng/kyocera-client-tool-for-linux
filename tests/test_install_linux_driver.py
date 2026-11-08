from __future__ import annotations

import contextlib
import io
import unittest
from pathlib import Path
from unittest import mock

from kyocera_monitor.usb import UsbPrinter
from tools import install_linux_driver


class InstallLinuxDriverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.printer = UsbPrinter(
            device="/dev/usb/lp0",
            vendor_id=0x0482,
            product_id=0x0D51,
            manufacturer="Kyocera",
            product="MA2000w",
            serial="ABC123",
        )
        self.uri = "usb://Kyocera/MA2000w?serial=ABC123"

    def _run(self, *arguments: str):
        with (
            mock.patch.object(
                install_linux_driver,
                "discover_usb_printers",
                return_value=[self.printer],
            ),
            mock.patch.object(
                install_linux_driver,
                "discover_libusb_printers",
                return_value=[],
            ),
            mock.patch.object(
                install_linux_driver,
                "queue_devices",
                return_value=self.queues,
            ),
            mock.patch.object(
                install_linux_driver,
                "choose_ppd",
                return_value=Path("/test/Kyocera_MA2000w.ppd"),
            ),
            mock.patch.object(
                install_linux_driver.shutil,
                "which",
                side_effect=lambda name: f"/usr/sbin/{name}",
            ),
            mock.patch.object(
                install_linux_driver.subprocess,
                "run",
                return_value=mock.Mock(returncode=0, stdout="", stderr=""),
            ) as run,
        ):
            with (
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                code = install_linux_driver.main(arguments)
        return code, run

    def test_existing_queue_with_another_uri_requires_force(self) -> None:
        self.queues = {"Kyocera-MA2000w": "usb://Other/Printer"}

        code, run = self._run("--apply")

        self.assertEqual(code, 2)
        run.assert_not_called()

    def test_force_replaces_existing_queue_with_another_uri(self) -> None:
        self.queues = {"Kyocera-MA2000w": "usb://Other/Printer"}

        code, run = self._run("--apply", "--force")

        self.assertEqual(code, 0)
        self.assertEqual(run.call_count, 3)
        self.assertEqual(
            run.call_args_list[0].args[0][:5],
            [
                "/usr/sbin/lpadmin",
                "-p",
                "Kyocera-MA2000w",
                "-E",
                "-v",
            ],
        )
        self.assertEqual(run.call_args_list[0].args[0][5], self.uri)

    def test_dry_run_reports_the_exact_queue_update(self) -> None:
        self.queues = {}

        code, run = self._run()

        self.assertEqual(code, 0)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
