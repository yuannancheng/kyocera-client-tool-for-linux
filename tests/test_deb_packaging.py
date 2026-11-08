import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(shutil.which("dpkg-deb"), "dpkg-deb is unavailable")
class DebianPackageTests(unittest.TestCase):
    def test_builds_installable_all_architecture_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    "python3",
                    str(ROOT / "tools" / "build_deb.py"),
                    "--output-dir",
                    tmp,
                    "--version",
                    "9.8.7",
                    "--revision",
                    "2",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=True,
            )
            package = Path(result.stdout.strip())
            self.assertTrue(package.is_file())
            self.assertEqual(package.name, "kyocera-monitor_9.8.7-2_all.deb")

            info = subprocess.run(
                ["dpkg-deb", "--field", str(package), "Package", "Architecture", "Depends"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            self.assertIn("Package: kyocera-monitor", info)
            self.assertIn("Architecture: all", info)
            self.assertIn("python3-pil", info)
            self.assertIn("libusb-1.0-0", info)
            self.assertIn("cups-client", info)

            contents = subprocess.run(
                ["dpkg-deb", "--contents", str(package)],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            for path in (
                "./usr/bin/kyocera-monitor",
                "./usr/bin/kyocera-gui",
                "./usr/bin/kyocera-kmscn-probe",
                "./usr/lib/python3/dist-packages/kyocera_monitor/scan.py",
                "./usr/lib/python3/dist-packages/kyocera_monitor/_build_version.py",
                "./usr/lib/python3/dist-packages/kyocera_monitor/usb_libusb.py",
                "./usr/lib/python3/dist-packages/kyocera_monitor/usb_scan.py",
                "./usr/lib/python3/dist-packages/kyocera_monitor/wifi.py",
                "./usr/share/applications/kyocera-monitor.desktop",
                "./usr/share/icons/hicolor/scalable/apps/kyocera-monitor.svg",
                "./usr/lib/udev/rules.d/90-kyocera-usb.rules",
                "./usr/libexec/kyocera-monitor/install-linux-driver",
                "./usr/share/doc/kyocera-monitor/LICENSE",
                "./usr/share/doc/kyocera-monitor/README.md",
                "./usr/share/doc/kyocera-monitor/README.en.md",
                "./usr/share/doc/kyocera-monitor/install_linux_driver.py",
            ):
                self.assertIn(path, contents)
            self.assertNotIn("Kyocera/ClientTool", contents)
            self.assertNotIn(".pyc", contents)

            extracted = Path(tmp) / "root"
            subprocess.run(
                ["dpkg-deb", "--extract", str(package), str(extracted)],
                check=True,
            )
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(
                extracted / "usr" / "lib" / "python3" / "dist-packages"
            )
            build_version = (
                extracted
                / "usr"
                / "lib"
                / "python3"
                / "dist-packages"
                / "kyocera_monitor"
                / "_build_version.py"
            ).read_text(encoding="utf-8")
            self.assertIn('__version__ = "9.8.7"', build_version)
            helper = subprocess.run(
                [
                    str(
                        extracted
                        / "usr"
                        / "libexec"
                        / "kyocera-monitor"
                        / "install-linux-driver"
                    ),
                    "--help",
                ],
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertIn("inspect or install a CUPS USB queue", helper.stdout)


if __name__ == "__main__":
    unittest.main()
