"""Regression coverage for preserving partial files and known video task IDs."""

from __future__ import annotations

import argparse
from email.message import Message
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "relay-media" / "scripts" / "media.py"
SPEC = importlib.util.spec_from_file_location("relay_media_review", SCRIPT)
media = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(media)
PNG = b"\x89PNG\r\n\x1a\n" + b"image-download-fixture"


class MediaResponse(io.BytesIO):
    def __init__(self, content: bytes = PNG):
        super().__init__(content)
        self.headers = Message()
        self.headers["Content-Type"] = "image/png"


class MediaReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="relay-review-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def client(self):
        client = media.Client("https://relay.invalid/v1", "test-only-key")
        client.opener = SimpleNamespace(open=mock.Mock(side_effect=lambda *args, **kwargs: MediaResponse()))
        return client

    def test_existing_partial_file_survives_successful_download(self) -> None:
        target = self.root / "image-01"
        partial = target.with_suffix(".part")
        partial.write_bytes(b"previous resumable download")
        client = self.client()
        result = client.download("/generated/image", target, "image", 1, 1024)
        self.assertEqual(result, target.with_suffix(".png"))
        self.assertEqual(result.read_bytes(), PNG)
        self.assertEqual(partial.read_bytes(), b"previous resumable download")
        self.assertEqual(set(self.root.iterdir()), {partial, result})

    def test_colliding_temporary_partial_file_is_not_deleted(self) -> None:
        target = self.root / "image-02"
        partial = target.with_name(target.name + "-fixed-unique-id.part")
        partial.write_bytes(b"another invocation owns these bytes")
        client = self.client()
        with mock.patch.object(media.uuid, "uuid4", return_value=SimpleNamespace(hex="fixed-unique-id")):
            with self.assertRaisesRegex(media.MediaError, "Media download failed"):
                client.download("/generated/image", target, "image", 1, 1024)
        self.assertEqual(partial.read_bytes(), b"another invocation owns these bytes")
        self.assertEqual(list(self.root.iterdir()), [partial])

    def test_status_recovers_known_id_when_response_ids_are_null(self) -> None:
        args = media.parser().parse_args([
            "--base-url", "https://relay.invalid/v1", "status", "known-job", "--no-download",
            "--output-dir", str(self.root / "outputs"),
        ])
        response = {"data": {"id": None, "task_id": None, "taskId": None, "status": "completed"}}
        with mock.patch.dict(media.os.environ, {"RELAY_API_KEY": "test-only-key"}, clear=True):
            with mock.patch.object(media.Client, "request", return_value=response) as request:
                result = media.execute(args)
        request.assert_called_once_with("GET", "videos/known-job")
        self.assertEqual(result["task_id"], "known-job")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["files"], [])
        saved = json.loads(Path(result["job_file"]).read_text(encoding="utf-8"))
        self.assertEqual(saved["task_id"], "known-job")
        self.assertEqual(saved["response"]["data"]["id"], "known-job")

    def test_polling_keeps_known_id_through_null_id_responses(self) -> None:
        client = SimpleNamespace(
            key="test-only-key",
            request=mock.Mock(side_effect=[
                {"id": None, "task_id": None, "taskId": None, "status": "processing"},
                {"data": {"id": None, "status": "completed"}},
            ]),
            endpoint=lambda path: "https://relay.invalid/v1/" + path,
        )
        args = argparse.Namespace(wait_timeout=1, wait=True, poll_interval=0.001, no_download=True)
        result = media.video_result(client, {"id": "poll-job", "status": "queued"}, args, self.root)
        self.assertEqual(client.request.call_args_list, [
            mock.call("GET", "videos/poll-job"),
            mock.call("GET", "videos/poll-job"),
        ])
        self.assertEqual(result["task_id"], "poll-job")
        self.assertEqual(result["status"], "completed")
        saved = json.loads(Path(result["job_file"]).read_text(encoding="utf-8"))
        self.assertEqual(saved["task_id"], "poll-job")
        self.assertEqual(saved["response"]["data"]["id"], "poll-job")


if __name__ == "__main__":
    unittest.main()
