import tempfile
import unittest
from pathlib import Path

from tools.install_desktop import install, target_paths, uninstall


class DesktopPackagingTests(unittest.TestCase):
    def test_install_writes_desktop_entry_and_icon(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory)
            desktop, icon = target_paths(prefix)
            installed = install(prefix)
            self.assertEqual(installed, [desktop, icon])
            text = desktop.read_text(encoding="utf-8")
            self.assertIn("[Desktop Entry]", text)
            self.assertIn("Type=Application", text)
            self.assertIn("Name=KYOCERA Client Tool for Linux", text)
            self.assertIn("Exec=kyocera-gui", text)
            self.assertIn("TryExec=kyocera-gui", text)
            self.assertIn("Icon=kyocera-monitor", text)
            self.assertIn("Categories=Settings;HardwareSettings;", text)
            self.assertTrue(icon.read_text(encoding="utf-8").startswith("<?xml"))
            self.assertIn("<svg", icon.read_text(encoding="utf-8"))

    def test_install_is_idempotent_and_refuses_conflicts(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory)
            desktop, _ = target_paths(prefix)
            install(prefix)
            install(prefix)
            desktop.write_text("changed\n", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                install(prefix)
            install(prefix, force=True)
            self.assertIn("Exec=kyocera-gui", desktop.read_text(encoding="utf-8"))

    def test_uninstall_removes_only_installed_files(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory)
            desktop, icon = target_paths(prefix)
            install(prefix)
            unrelated = prefix / "share" / "applications" / "keep.txt"
            unrelated.write_text("keep", encoding="utf-8")
            removed = uninstall(prefix)
            self.assertEqual(removed, [desktop, icon])
            self.assertFalse(desktop.exists())
            self.assertFalse(icon.exists())
            self.assertTrue(unrelated.exists())


if __name__ == "__main__":
    unittest.main()
