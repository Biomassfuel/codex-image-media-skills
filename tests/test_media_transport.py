"""Exercise connection termination using loopback servers and a synthetic key."""

from __future__ import annotations

import base64
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest


CLI = Path(__file__).resolve().parents[1] / "skills" / "relay-media" / "scripts" / "media.py"
TEST_KEY = "local-transport-test-key-never-print-this"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6"
    "rXIAAAAASUVORK5CYII="
)


@contextmanager
def local_server(mode: str):
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            declared = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(declared)
            received.append({"method": self.command, "path": self.path, "declared": declared, "body": body})
            if mode == "truncated-length":
                payload = b'{"data":[{"b64_json":"unfinished'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload) + 100))
                self.end_headers()
                self.wfile.write(payload)
                self.wfile.flush()
            elif mode == "truncated-chunk":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                # Advertise a 128-byte chunk, then terminate after only eight bytes.
                self.wfile.write(b'80\r\n{"data":')
                self.wfile.flush()
            elif mode in {"image-success", "proxy-error"}:
                value = {"data": [{"b64_json": base64.b64encode(PNG).decode()}]} if mode == "image-success" else {"error": "local proxy deliberately rejected this request"}
                payload = json.dumps(value).encode("utf-8")
                self.send_response(200 if mode == "image-success" else 502)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                self.wfile.flush()
            elif mode != "before-status":
                raise AssertionError(f"Unknown test mode: {mode}")
            self.close_connection = True
            self.connection.shutdown(socket.SHUT_RDWR)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", received
    finally:
        server.shutdown()
        worker.join(timeout=2)
        server.server_close()


class MediaTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="relay-transport-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def run_cli(self, base: str, *, no_proxy: bool = False, proxy: str | None = None):
        environment = {
            name: value
            for name, value in os.environ.items()
            if not name.startswith("RELAY_")
            and name.lower() not in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}
        }
        environment["RELAY_API_KEY"] = TEST_KEY
        environment["NO_PROXY"] = "" if proxy else "127.0.0.1,localhost"
        if proxy:
            environment["HTTP_PROXY"] = proxy
            environment["HTTPS_PROXY"] = proxy
        global_options = ["--base-url", base, "--timeout", "3"]
        if no_proxy:
            global_options.append("--no-proxy")
        return subprocess.run(
            [sys.executable, str(CLI), *global_options, "image", "--model", "gpt-image-2.5",
             "--prompt", "offline loopback transport regression", "--output-dir", str(self.root / "outputs")],
            cwd=self.root, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=10,
        )

    def assert_one_complete_post(self, received) -> None:
        self.assertEqual(len(received), 1, "A failed creation must not be submitted again automatically")
        request = received[0]
        self.assertEqual(request["method"], "POST")
        self.assertEqual(request["path"], "/v1/images/generations")
        self.assertEqual(request["declared"], len(request["body"]))
        self.assertEqual(json.loads(request["body"])["model"], "gpt-image-2.5")

    def assert_controlled_error(self, process) -> dict:
        self.assertEqual(process.returncode, 1)
        self.assertEqual(process.stdout, "")
        self.assertNotIn(TEST_KEY, process.stdout + process.stderr)
        self.assertNotIn("Traceback", process.stderr, process.stderr)
        result = json.loads(process.stderr)
        self.assertIsInstance(result.get("error"), str)
        self.assertTrue(result["error"].strip())
        snapshots = list((self.root / "outputs").glob("*/failure.json"))
        self.assertEqual(len(snapshots), 1, "The failed creation should leave one local failure snapshot")
        self.assertIsInstance(json.loads(snapshots[0].read_text(encoding="utf-8")), dict)
        for path in (self.root / "outputs").rglob("*"):
            if path.is_file():
                self.assertNotIn(TEST_KEY.encode(), path.read_bytes(), str(path))
        return result

    def test_connection_closes_before_status_without_retry_or_key_leak(self) -> None:
        with local_server("before-status") as (base, received):
            process = self.run_cli(base)
        self.assert_one_complete_post(received)
        self.assert_controlled_error(process)

    def test_content_length_body_is_truncated_without_retry_or_key_leak(self) -> None:
        with local_server("truncated-length") as (base, received):
            process = self.run_cli(base)
        self.assert_one_complete_post(received)
        self.assert_controlled_error(process)

    def test_chunked_body_is_truncated_without_retry_or_key_leak(self) -> None:
        with local_server("truncated-chunk") as (base, received):
            process = self.run_cli(base)
        self.assert_one_complete_post(received)
        self.assert_controlled_error(process)

    def test_no_proxy_bypasses_an_environment_proxy_that_rejects_requests(self) -> None:
        with local_server("image-success") as (base, origin_requests):
            with local_server("proxy-error") as (proxy, proxy_requests):
                rejected = self.run_cli(base, proxy=proxy)
                self.assert_controlled_error(rejected)
                self.assertEqual(len(proxy_requests), 1)
                self.assertEqual(origin_requests, [])
                self.assertTrue(proxy_requests[0]["path"].startswith(base + "/v1/"))

                direct = self.run_cli(base, proxy=proxy, no_proxy=True)
        self.assertEqual(direct.returncode, 0, direct.stderr)
        self.assertEqual(direct.stderr, "")
        self.assertNotIn(TEST_KEY, direct.stdout + direct.stderr)
        self.assertEqual(len(proxy_requests), 1, "The direct request must not contact the configured proxy")
        self.assert_one_complete_post(origin_requests)
        result = json.loads(direct.stdout)
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(Path(result["files"][0]).read_bytes(), PNG)


if __name__ == "__main__":
    unittest.main()
