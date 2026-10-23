"""Local HTTP integration tests for the relay CLI; no real provider is contacted."""

from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest


CLI = Path(__file__).resolve().parents[1] / "skills" / "relay-media" / "scripts" / "media.py"
SECRET = "test-private-key-do-not-save-12345"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6"
    "rXIAAAAASUVORK5CYII="
)
VIDEO = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + b"test-video-fixture"


@dataclass
class Request:
    method: str
    path: str
    headers: dict[str, str]
    body: bytes

    def json(self):
        return json.loads(self.body)

    def parts(self):
        message = BytesParser(policy=policy.default).parsebytes(
            ("Content-Type: " + self.headers["content-type"] + "\r\nMIME-Version: 1.0\r\n\r\n").encode()
            + self.body
        )
        return [
            (part.get_param("name", header="content-disposition"), part.get_filename(), part.get_payload(decode=True))
            for part in message.iter_parts()
        ]


def reply_json(value, code=200):
    return code, {"Content-Type": "application/json"}, json.dumps(value).encode()


@contextmanager
def relay(respond):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def handle_request(self):
            request = Request(
                self.command,
                self.path,
                {key.lower(): value for key, value in self.headers.items()},
                self.rfile.read(int(self.headers.get("Content-Length", 0))),
            )
            requests.append(request)
            try:
                status, headers, body = respond(request)
            except Exception as exc:
                status, headers, body = reply_json({"unexpected_test_request": str(exc)}, 500)
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = handle_request
        do_POST = handle_request

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


class MediaCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="relay-cli-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = self.root / "outputs"

    def run_cli(self, *args, base=None, key=SECRET):
        env = {
            name: value
            for name, value in os.environ.items()
            if not name.startswith("RELAY_")
            and name.lower() not in {"http_proxy", "https_proxy", "all_proxy"}
        }
        env["PYTHONIOENCODING"] = "utf-8"
        env["NO_PROXY"] = "127.0.0.1,localhost"
        if key is not None:
            env["RELAY_API_KEY"] = key
        command = [sys.executable, str(CLI)]
        if base:
            command.extend(["--base-url", base])
        command.extend(args)
        return subprocess.run(command, cwd=self.root, env=env, capture_output=True, text=True, encoding="utf-8", timeout=15)

    def success(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def output_args(self):
        return ["--output-dir", str(self.output)]

    def assert_secret_absent(self, result):
        self.assertNotIn(SECRET, result.stdout + result.stderr)
        if self.output.exists():
            for path in self.output.rglob("*"):
                if path.is_file():
                    self.assertNotIn(SECRET.encode(), path.read_bytes(), str(path))

    def test_image_json_base64_saved_and_alias_resolved(self):
        with relay(lambda request: reply_json({"data": [{"b64_json": base64.b64encode(PNG).decode()}]})) as (base, requests):
            process = self.run_cli("image", "--model", "image2", "--prompt", "a red apple", *self.output_args(), base=base)
        result = self.success(process)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].path, "/v1/images/generations")
        self.assertEqual(requests[0].headers["authorization"], "Bearer " + SECRET)
        self.assertEqual(requests[0].json(), {"model": "gpt-image-2", "prompt": "a red apple", "n": 1})
        self.assertEqual(result["model"], "gpt-image-2")
        self.assertEqual(Path(result["files"][0]).read_bytes(), PNG)
        self.assertEqual(Path(result["files"][0]).suffix, ".png")
        self.assert_secret_absent(process)

    def test_multiple_reference_images_and_mask_are_multipart(self):
        first, second, mask = [self.root / filename for filename in ("first.png", "second.png", "mask.png")]
        for index, path in enumerate((first, second, mask)):
            path.write_bytes(PNG + bytes([index]))
        with relay(lambda request: reply_json({"data": [{"b64_json": base64.b64encode(PNG).decode()}]})) as (base, requests):
            process = self.run_cli(
                "image", "--model", "gpt-image-2.5-flare", "--prompt", "combine these", "--image", str(first),
                "--image", str(second), "--mask", str(mask), "--extra-json", '{"provider_options":{"seed":7}}',
                *self.output_args(), base=base,
            )
        self.success(process)
        self.assertEqual(requests[0].path, "/v1/images/edits")
        parts = requests[0].parts()
        images = [(filename, data) for name, filename, data in parts if name == "image[]"]
        self.assertEqual(images, [(first.name, first.read_bytes()), (second.name, second.read_bytes())])
        self.assertEqual([(name, data) for name, _, data in parts if name == "mask"], [("mask", mask.read_bytes())])
        fields = {name: data.decode() for name, filename, data in parts if filename is None}
        self.assertEqual(fields["model"], "gpt-image-2.5-flare")
        self.assertEqual(json.loads(fields["provider_options"]), {"seed": 7})

    def test_image_url_downloads_bytes(self):
        def respond(request):
            if request.method == "POST":
                return reply_json({"data": [{"url": "/assets/generated"}]})
            return 200, {"Content-Type": "image/png"}, PNG

        with relay(respond) as (base, requests):
            process = self.run_cli("image", "--prompt", "a cloud", *self.output_args(), base=base)
        result = self.success(process)
        self.assertEqual([request.path for request in requests], ["/v1/images/generations", "/assets/generated"])
        self.assertEqual(Path(result["files"][0]).read_bytes(), PNG)

    def test_video_creates_once_polls_then_downloads_content(self):
        def respond(request):
            if request.method == "POST":
                return reply_json({"id": "job-7", "status": "queued"})
            if request.path.endswith("/content"):
                return 200, {"Content-Type": "video/mp4"}, VIDEO
            return reply_json({"id": "job-7", "status": "completed", "progress": 100})

        with relay(respond) as (base, requests):
            process = self.run_cli(
                "video", "--model", "seedance-2.5", "--prompt", "a flying bird", "--seconds", "6", "--wait",
                "--poll-interval", "0.01", "--wait-timeout", "2", *self.output_args(), base=base,
            )
        result = self.success(process)
        self.assertEqual([request.method for request in requests], ["POST", "GET", "GET"])
        self.assertEqual([request.path for request in requests], ["/v1/videos", "/v1/videos/job-7", "/v1/videos/job-7/content"])
        self.assertEqual(requests[0].json()["duration"], 6)
        self.assertNotIn("seconds", requests[0].json())
        self.assertEqual(result["task_id"], "job-7")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(Path(result["files"][0]).read_bytes(), VIDEO)
        self.assertEqual(json.loads(Path(result["job_file"]).read_text())["status"], "completed")

    def test_status_resumes_without_submission_and_supplies_missing_id(self):
        def respond(request):
            if request.path.endswith("/content"):
                return 200, {"Content-Type": "video/mp4"}, VIDEO
            return reply_json({"data": {"status": "succeeded"}})

        with relay(respond) as (base, requests):
            process = self.run_cli("status", "existing-job", *self.output_args(), base=base)
        result = self.success(process)
        self.assertEqual([request.method for request in requests], ["GET", "GET"])
        self.assertEqual(result["task_id"], "existing-job")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(Path(result["files"][0]).read_bytes(), VIDEO)

    def test_pending_video_persists_task_for_later_status(self):
        with relay(lambda request: reply_json({"data": {"task_id": "later-job", "state": "pending"}})) as (base, requests):
            process = self.run_cli("video", "--model", "custom-video", "--prompt", "a wave", *self.output_args(), base=base)
        result = self.success(process)
        self.assertEqual(len(requests), 1)
        self.assertTrue(result["pending"])
        self.assertEqual(result["task_id"], "later-job")
        self.assertEqual(json.loads(Path(result["job_file"]).read_text())["task_id"], "later-job")

    def test_failed_video_preserves_task_and_redacts_error(self):
        failure = {"id": "failed-job", "status": "failed", "error": {"code": "blocked", "message": "refused key " + SECRET}}
        with relay(lambda request: reply_json(failure)) as (base, requests):
            process = self.run_cli("video", "--model", "custom-video", "--prompt", "a wave", *self.output_args(), base=base)
        self.assertEqual(process.returncode, 1)
        self.assertEqual(len(requests), 1)
        jobs = list(self.output.glob("*/job.json"))
        self.assertEqual(len(jobs), 1, process.stderr)
        saved = json.loads(jobs[0].read_text())
        self.assertEqual(saved["task_id"], "failed-job")
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["error"]["code"], "blocked")
        self.assert_secret_absent(process)

    def test_poll_failure_updates_saved_job(self):
        def respond(request):
            if request.method == "POST":
                return reply_json({"id": "poll-failed", "status": "queued"})
            return reply_json({"id": "poll-failed", "status": "failed", "error": {"message": "quota " + SECRET}})

        with relay(respond) as (base, requests):
            process = self.run_cli(
                "video", "--model", "custom-video", "--prompt", "a wave", "--wait", "--poll-interval", "0.01",
                "--wait-timeout", "2", *self.output_args(), base=base,
            )
        self.assertEqual(process.returncode, 1)
        self.assertEqual([request.method for request in requests], ["POST", "GET"])
        saved = json.loads(next(self.output.glob("*/job.json")).read_text())
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["task_id"], "poll-failed")
        self.assert_secret_absent(process)

    def test_dry_run_has_no_key_network_or_output_directory(self):
        with relay(lambda request: reply_json({"unexpected": True}, 500)) as (base, requests):
            for command in (
                ["image", "--prompt", "a cloud"],
                ["video", "--model", "future-video-model", "--prompt", "a wave"],
            ):
                with self.subTest(command=command):
                    process = self.run_cli(*command, "--dry-run", *self.output_args(), base=base, key=None)
                    result = self.success(process)
                    self.assertTrue(result["dry_run"])
                    self.assertFalse(self.output.exists())
        self.assertEqual(requests, [])

    def test_models_are_passed_through_and_image2_is_the_only_alias(self):
        for supplied, expected in (
            ("image2", "gpt-image-2"),
            ("gpt-image-2", "gpt-image-2"),
            ("gpt-image-2.5", "gpt-image-2.5"),
            ("gpt-image-2.5-flare", "gpt-image-2.5-flare"),
            ("gpt-image-2.5-sunburst", "gpt-image-2.5-sunburst"),
            ("my-provider/custom-model-v9", "my-provider/custom-model-v9"),
        ):
            with self.subTest(model=supplied):
                result = self.success(self.run_cli("image", "--model", supplied, "--prompt", "a cloud", "--dry-run", key=None))
                self.assertEqual(result["body"]["model"], expected)

    def test_extra_json_preserves_nested_provider_fields(self):
        extras = {"seed": 42, "generate_audio": False, "provider": {"mode": "fast", "values": [1, 2]}}
        with relay(lambda request: reply_json({"id": "extra-job", "status": "queued"})) as (base, requests):
            process = self.run_cli(
                "video", "--model", "future-video", "--prompt", "a train", "--extra-json", json.dumps(extras),
                "--reference-image-url", "https://assets.example/image.png", *self.output_args(), base=base,
            )
        self.success(process)
        body = requests[0].json()
        for key, value in extras.items():
            self.assertEqual(body[key], value)
        self.assertEqual(body["reference_image_urls"], ["https://assets.example/image.png"])

    def test_local_video_reference_uses_input_reference_multipart(self):
        reference = self.root / "reference.png"
        reference.write_bytes(PNG)
        with relay(lambda request: reply_json({"id": "grok-job", "status": "queued"})) as (base, requests):
            process = self.run_cli(
                "video", "--model", "grok-imagine-video", "--prompt", "animate", "--seconds", "5", "--image",
                str(reference), *self.output_args(), base=base,
            )
        self.success(process)
        parts = requests[0].parts()
        self.assertEqual([(name, payload) for name, filename, payload in parts if filename], [("input_reference", PNG)])
        fields = {name: payload.decode() for name, filename, payload in parts if filename is None}
        self.assertEqual(fields["seconds"], "5")

    def test_explicit_video_multipart_preserves_fields_without_reference_file(self):
        with relay(lambda request: reply_json({"id": "multipart-job", "status": "queued"})) as (base, requests):
            process = self.run_cli(
                "video", "--model", "custom-video", "--prompt", "a moon", "--encoding", "multipart", "--seconds", "8",
                "--extra-json", '{"generate_audio":false,"options":{"seed":3}}', *self.output_args(), base=base,
            )
        self.success(process)
        parts = requests[0].parts()
        self.assertTrue(parts)
        self.assertFalse(any(filename for _, filename, _ in parts))
        fields = {name: payload.decode() for name, _, payload in parts}
        self.assertEqual(fields["model"], "custom-video")
        self.assertEqual(fields["seconds"], "8")
        self.assertFalse(json.loads(fields["generate_audio"]))
        self.assertEqual(json.loads(fields["options"]), {"seed": 3})

    def test_download_redirect_never_forwards_key_to_another_origin(self):
        with relay(lambda request: (200, {"Content-Type": "image/png"}, PNG)) as (asset_base, asset_requests):
            def respond(request):
                if request.method == "POST":
                    return reply_json({"data": [{"url": "/asset-redirect"}]})
                return 302, {"Location": asset_base + "/public-image"}, b""

            with relay(respond) as (base, requests):
                process = self.run_cli("image", "--prompt", "a lake", *self.output_args(), base=base)
        result = self.success(process)
        self.assertEqual(requests[-1].headers.get("authorization"), "Bearer " + SECRET)
        self.assertEqual(len(asset_requests), 1)
        self.assertNotIn("authorization", asset_requests[0].headers)
        self.assertEqual(Path(result["files"][0]).read_bytes(), PNG)

    def test_http_failure_redacts_key_and_does_not_retry_creation(self):
        with relay(lambda request: reply_json({"error": {"message": "bad credential " + SECRET}}, 503)) as (base, requests):
            process = self.run_cli("image", "--prompt", "a cloud", *self.output_args(), base=base)
        self.assertEqual(process.returncode, 1)
        self.assertEqual(len(requests), 1)
        self.assertIn("503", process.stderr)
        self.assert_secret_absent(process)

    def test_video_server_error_does_not_create_a_second_billable_task(self):
        for encoding in ("json", "multipart"):
            with self.subTest(encoding=encoding):
                with relay(lambda request: reply_json({"error": {"message": "gateway unavailable " + SECRET}}, 503)) as (base, requests):
                    process = self.run_cli(
                        "video", "--model", "custom-video", "--prompt", "a wave", "--encoding", encoding,
                        *self.output_args(), base=base,
                    )
                self.assertEqual(process.returncode, 1)
                self.assertEqual(len(requests), 1)
                self.assertEqual(requests[0].method, "POST")
                self.assertIn("not retried", process.stderr)
                self.assert_secret_absent(process)

    def test_success_response_metadata_is_redacted_on_disk(self):
        response = {
            "data": [{"b64_json": base64.b64encode(PNG).decode()}],
            "api_key": SECRET,
            "metadata": {"access_token": SECRET, "message": "provider reflected " + SECRET},
        }
        with relay(lambda request: reply_json(response)) as (base, _):
            process = self.run_cli("image", "--prompt", "a cloud", *self.output_args(), base=base)
        self.success(process)
        self.assert_secret_absent(process)

    def test_html_download_is_rejected_for_both_image_and_video(self):
        for command in ("image", "video"):
            with self.subTest(command=command):
                output = self.root / (command + "-html")

                def respond(request):
                    if request.method == "POST":
                        if command == "image":
                            return reply_json({"data": [{"url": "/html-result"}]})
                        return reply_json({"id": "html-job", "status": "completed", "url": "/html-result"})
                    return 200, {"Content-Type": "text/html"}, b"<!doctype html><html>login required</html>"

                with relay(respond) as (base, _):
                    args = [command, "--prompt", "a cloud", "--output-dir", str(output)]
                    if command == "video":
                        args.extend(["--model", "custom-video"])
                    process = self.run_cli(*args, base=base)
                self.assertEqual(process.returncode, 1)
                self.assertIn("recognized media file", process.stderr)
                self.assertFalse(list(output.rglob("*.png")))
                self.assertFalse(list(output.rglob("*.mp4")))
                self.assertFalse(list(output.rglob("*.part")))


if __name__ == "__main__":
    unittest.main()
