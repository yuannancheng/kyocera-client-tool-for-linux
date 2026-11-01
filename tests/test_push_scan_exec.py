import unittest
from pathlib import Path
from unittest import mock

from kyocera_monitor.preferences import normalize_settings
from kyocera_monitor.push_scan_exec import execute_push_scan_event
from kyocera_monitor.scan import ScanBusyError

READY_PUSH_STATE = {
    "readiness": {
        "ready": True,
        "state": "ready",
    }
}


class FakeJob:
    def __init__(self, job_id="job-1", state="succeeded"):
        self.job_id = job_id
        self.state = state

    def metadata(self):
        return {
            "job_id": self.job_id,
            "state": self.state,
            "saved_paths": ["/tmp/scans/result.pdf"],
        }


def settings_with_slot(slot=3):
    return normalize_settings(
        {
            "scan_directory": "/tmp/scans",
            "presets": [
                {
                    "id": "folder-pdf",
                    "name": "Folder PDF",
                    "color": "GRAYSCALE",
                    "resolution": "RESOLUTION_300X300",
                    "original_image": "TEXT",
                    "max_pages": 2,
                    "output_format": "pdf",
                    "push_scan_slot": slot,
                }
            ],
        }
    )


class PushScanExecutionTests(unittest.TestCase):
    def test_unmapped_slot_does_not_start_a_scan(self):
        manager = mock.Mock()
        result = execute_push_scan_event(
            {"host": "192.0.2.1", "preset_number": 4},
            settings_with_slot(3),
            manager,
            push_state=READY_PUSH_STATE,
        )
        self.assertEqual(result["status"], "unmapped")
        self.assertEqual(result["result_writeback"], "not_attempted")
        manager.start.assert_not_called()

    def test_mapped_slot_runs_the_normal_scan_job(self):
        manager = mock.Mock()
        job = FakeJob()
        manager.start.return_value = job
        manager.wait.return_value = job
        event = {
            "host": "192.0.2.1",
            "preset_number": 3,
        }

        result = execute_push_scan_event(
            event,
            settings_with_slot(3),
            manager,
            push_state=READY_PUSH_STATE,
        )

        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["preset"]["id"], "folder-pdf")
        self.assertEqual(result["result_writeback"], "not_attempted")
        manager.start.assert_called_once()
        host, options = manager.start.call_args.args
        self.assertEqual(host, "192.0.2.1")
        self.assertEqual(options.color, "GRAYSCALE")
        self.assertEqual(options.resolution, "RESOLUTION_300X300")
        self.assertEqual(options.max_pages, 2)
        self.assertEqual(options.output_format, "pdf")
        self.assertEqual(
            manager.start.call_args.kwargs["output_directory"],
            Path("/tmp/scans"),
        )
        manager.wait.assert_called_once_with(job.job_id, timeout=mock.ANY)

    def test_busy_slot_is_reported_without_claiming_a_result(self):
        manager = mock.Mock()
        manager.start.side_effect = ScanBusyError("busy")
        result = execute_push_scan_event(
            {"host": "192.0.2.1", "preset_number": 3},
            settings_with_slot(3),
            manager,
            push_state=READY_PUSH_STATE,
        )
        self.assertEqual(result["status"], "busy")
        self.assertEqual(result["result_writeback"], "not_attempted")
        manager.wait.assert_not_called()

    def test_non_ready_device_does_not_start_a_scan(self):
        manager = mock.Mock()
        result = execute_push_scan_event(
            {"host": "192.0.2.1", "preset_number": 3},
            settings_with_slot(3),
            manager,
            push_state={
                "readiness": {
                    "ready": False,
                    "state": "other_host",
                }
            },
        )
        self.assertEqual(result["status"], "not_ready")
        self.assertEqual(result["readiness_state"], "other_host")
        self.assertEqual(result["result_writeback"], "not_attempted")
        manager.start.assert_not_called()

    def test_invalid_event_is_rejected(self):
        manager = mock.Mock()
        with self.assertRaises(ValueError):
            execute_push_scan_event(
                {"host": "", "preset_number": 3},
                settings_with_slot(3),
                manager,
                push_state=READY_PUSH_STATE,
            )


if __name__ == "__main__":
    unittest.main()
