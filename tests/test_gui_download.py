import json
import os
import stat
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from kyocera_monitor import gui
from kyocera_monitor.scan import ScanArtifact


def artifact(filename="scan.pdf", data=b"%PDF-test"):
    return ScanArtifact(
        filename=filename,
        media_type="application/pdf",
        kind="pdf",
        width=10,
        height=20,
        data=data,
    )


class DownloadPathTests(unittest.TestCase):
    def test_basename_and_unique_destination_are_safe(self):
        self.assertEqual(
            gui.safe_download_filename("../../bad\x00name.pdf"),
            "bad_name.pdf",
        )
        self.assertEqual(
            gui.safe_download_filename("C:\\fakepath\\scan.pdf"),
            "scan.pdf",
        )
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "Downloads"
            first_fd, first = gui.download_destination(directory, "scan.pdf")
            os.close(first_fd)
            second_fd, second = gui.download_destination(directory, "scan.pdf")
            os.close(second_fd)
            self.assertEqual(first.name, "scan.pdf")
            self.assertEqual(second.name, "scan-1.pdf")
            self.assertEqual(stat.S_IMODE(first.stat().st_mode), 0o600)

    def test_save_artifact_writes_exact_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            saved = gui.save_download_artifact(artifact(), Path(tmp))
            self.assertEqual(saved.read_bytes(), b"%PDF-test")
            self.assertEqual(stat.S_IMODE(saved.stat().st_mode), 0o600)

    def test_download_message_only_accepts_relative_artifact_url(self):
        job_id = "a" * 32
        parsed = gui.parse_download_request(
            {
                "url": f"/api/scans/{job_id}/files/2",
                "filename": "scan.pdf",
            }
        )
        self.assertEqual(parsed, (job_id, 2, "scan.pdf"))
        for url in (
            f"http://localhost/api/scans/{job_id}/files/2",
            f"/api/scans/{job_id}/files/2?x=1",
            "/api/scans/not-a-job/files/0",
            "/api/counters.csv",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    gui.parse_download_request(
                        {"url": url, "filename": "scan.pdf"}
                    )


class DownloadBridgeTests(unittest.TestCase):
    def test_bridge_saves_message_through_scan_manager(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_id = "b" * 32
            manager = mock.Mock()
            manager.output.return_value = artifact()
            content_manager = mock.Mock()

            class MessageValue:
                def to_json(self, _flags):
                    return json.dumps(
                        {
                            "url": f"/api/scans/{job_id}/files/0",
                            "filename": "scan.pdf",
                        }
                    )

            class Message:
                def get_js_value(self):
                    return MessageValue()

            class Window:
                def get_visible(self):
                    return True

            dialogs = []

            class MessageDialog:
                def __init__(self, **kwargs):
                    self.kwargs = kwargs
                    self.secondary = None
                    dialogs.append(self)

                def format_secondary_text(self, text):
                    self.secondary = text

                def connect(self, *_args):
                    return None

                def show(self):
                    return None

            Gtk = types.SimpleNamespace(
                MessageType=types.SimpleNamespace(INFO="info", ERROR="error"),
                ButtonsType=types.SimpleNamespace(OK="ok"),
                MessageDialog=MessageDialog,
            )

            class GLib:
                @staticmethod
                def idle_add(callback, *args, **kwargs):
                    callback(*args, **kwargs)
                    return 1

            class InlineThread:
                def __init__(self, target, **_kwargs):
                    self.target = target

                def start(self):
                    self.target()

            gui._install_download_bridge(
                Gtk,
                GLib,
                content_manager,
                manager,
                Window(),
                downloads_directory=Path(tmp),
            )
            content_manager.register_script_message_handler.assert_called_once_with(
                "kyoceraDownload"
            )
            callback = content_manager.connect.call_args.args[1]
            with mock.patch.object(gui.threading, "Thread", InlineThread):
                callback(content_manager, Message())
            manager.output.assert_called_once_with(job_id, 0)
            saved = Path(tmp) / "scan.pdf"
            self.assertEqual(saved.read_bytes(), b"%PDF-test")
            self.assertEqual(dialogs[0].kwargs["text"], "扫描文件已下载")
            self.assertEqual(dialogs[0].secondary, str(saved))


if __name__ == "__main__":
    unittest.main()
