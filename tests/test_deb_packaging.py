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
                "./usr/share/applications/kyocera-monitor.desktop",
                "./usr/share/icons/hicolor/scalable/apps/kyocera-monitor.svg",
                "./usr/share/doc/kyocera-monitor/LICENSE",
            ):
                self.assertIn(path, contents)
            self.assertNotIn("Kyocera/ClientTool", contents)
            self.assertNotIn(".pyc", contents)


if __name__ == "__main__":
    unittest.main()
