"""Catalog-driven parameter constraints and the offline interactive menu; no provider is contacted."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


CLI = Path(__file__).resolve().parents[1] / "skills" / "relay-media" / "scripts" / "media.py"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_media import PNG, relay, reply_json  # noqa: E402  (shared local relay fixture)

# A 1x1 GIF: recognized as an image, but its canvas cannot be read, so size reporting must skip it.
GIF = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")

# A 1024x1024 JPEG header: the upstream relay answers with JPEG, so its canvas must be read too.
JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xc0\x00\x11\x08\x04\x00\x04\x00\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    b"\xff\xd9"
)

SIZES = [
    "1024x1024",
    "1536x1024",
    "1024x1536",
    "1792x1024",
    "1024x1792",
    "2048x2048",
    "2048x1152",
    "1152x2048",
    "2560x1440",
    "1440x2560",
    "3840x2160",
    "2160x3840",
]


class ModelCatalogTests(unittest.TestCase):
    def run_cli(self, *args, base=None, unattended=True):
        env = {
            name: value
            for name, value in os.environ.items()
            if not name.startswith("RELAY_") and name.lower() not in {"http_proxy", "https_proxy", "all_proxy"}
        }
        env["PYTHONIOENCODING"] = "utf-8"
        env["NO_PROXY"] = "127.0.0.1,localhost"
        if base:
            env["RELAY_API_KEY"] = "catalog-test-key"
        command = [sys.executable, str(CLI)]
        if base:
            command.extend(["--base-url", base])
        command.extend(args)
        if unattended and "image" in args and "--unattended" not in args:
            command.append("--unattended")
        return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", env=env)

    def body(self, *args):
        process = self.run_cli(*args, "--dry-run")
        self.assertEqual(process.returncode, 0, process.stderr)
        return json.loads(process.stdout)["body"]

    def rejects(self, expected, *args):
        process = self.run_cli(*args, "--dry-run")
        self.assertNotEqual(process.returncode, 0, process.stdout)
        self.assertIn(expected, process.stderr)

    def test_catalog_lists_models_sorted_with_their_allowed_values(self):
        process = self.run_cli("catalog")
        self.assertEqual(process.returncode, 0, process.stderr)
        entries = json.loads(process.stdout)["models"]
        identifiers = [entry["id"] for entry in entries]
        self.assertEqual(identifiers, sorted(identifiers))
        self.assertIn("gpt-image-2", identifiers)
        profile = next(entry for entry in entries if entry["id"] == "gpt-image-2")
        self.assertEqual(profile["size"]["mode"], "enum")
        self.assertIn("1536x1024", profile["size"]["values"])
        self.assertIn("high", profile["quality"]["values"])
        self.assertEqual(profile["size_reliability"], "observed")
        self.assertIn("2048x2048", profile["size_note"])

    def test_catalog_offers_exactly_the_twelve_product_sizes_in_order(self):
        entries = json.loads(self.run_cli("catalog").stdout)["models"]
        for entry in entries:
            if entry["size"]["mode"] == "enum":
                self.assertEqual(entry["size"]["values"], SIZES, entry["id"])
                self.assertNotIn("auto", entry["size"]["values"], entry["id"])

    def test_choices_publishes_prompt_size_and_quality_menus(self):
        process = self.run_cli("choices", "--model", "gpt-image-2")
        self.assertEqual(process.returncode, 0, process.stderr)
        data = json.loads(process.stdout)
        self.assertTrue(data["cataloged"])
        self.assertEqual(data["menu_version"], "2026-10-24.4")
        self.assertFalse(data["model_required"])
        self.assertEqual([option["id"] for option in data["prompt"]["options"]], ["original", "optimized-1", "optimized-2", "optimized-3"])
        self.assertTrue(data["prompt"]["options"][1]["recommended"])
        self.assertFalse(data["prompt"]["options"][0]["recommended"])
        self.assertEqual([option["id"] for option in data["model_options"]], ["gpt-image-2.5", "gpt-image-2", "gpt-image-2.5-flare", "gpt-image-2.5-sunburst"])
        self.assertEqual([option["size_count"] for option in data["model_options"]], [12, 12, 12, 12])
        self.assertTrue(data["model_options"][0]["recommended"])
        self.assertEqual(data["model_options"][1]["size_reliability"], "observed")
        self.assertTrue(data["supplement"]["free_text"])
        self.assertTrue(data["supplement"]["examples"])
        self.assertEqual([option["value"] for option in data["size"]["options"]], SIZES)
        self.assertTrue(data["size"]["do_not_filter"])
        self.assertEqual(data["size"]["pages"], [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]])
        self.assertEqual([option["value"] for option in data["quality"]["options"]], ["auto", "low", "medium", "high"])
        self.assertEqual(data["size"]["default"], "1024x1024")
        self.assertEqual(data["quality"]["default"], "auto")
        self.assertTrue(next(option for option in data["size"]["options"] if option["value"] == "1024x1024")["recommended"])
        self.assertEqual(data["size"]["options"][6]["tier"], "2K")
        self.assertEqual(data["size"]["options"][8]["tier"], "4K")
        self.assertEqual(data["size"]["options"][6]["aspect"], "16:9")

    def test_choices_resolves_alias_and_sunburst_offers_sizes(self):
        alias = json.loads(self.run_cli("choices", "--model", "image2").stdout)
        self.assertEqual(alias["model"], "gpt-image-2")
        sunburst = json.loads(self.run_cli("choices", "--model", "gpt-image-2.5-sunburst").stdout)
        self.assertEqual(sunburst["size"]["mode"], "enum")
        self.assertEqual([option["value"] for option in sunburst["size"]["options"]], SIZES)
        self.assertEqual(sunburst["size"]["default"], "1024x1024")

    def test_choices_needs_no_key_or_network(self):
        process = self.run_cli("choices")
        self.assertEqual(process.returncode, 0, process.stderr)
        data = json.loads(process.stdout)
        self.assertEqual(data["menu_version"], "2026-10-24.4")
        self.assertTrue(data["model_required"])
        self.assertIsNone(data["model"])
        self.assertEqual(len(data["model_options"]), 4)
        self.assertEqual(data["size"]["mode"], "pending")
        selected = self.run_cli("choices", "--model", "gpt-image-2.5")
        self.assertEqual(selected.returncode, 0, selected.stderr)
        self.assertEqual(len(json.loads(selected.stdout)["size"]["options"]), 12)

    def test_choices_without_model_requires_a_model_choice(self):
        data = json.loads(self.run_cli("choices").stdout)
        self.assertTrue(data["model_required"])
        self.assertIsNone(data["model"])
        self.assertFalse(any(option["selected"] for option in data["model_options"]))
        self.assertEqual(data["size"]["mode"], "pending")
        self.assertEqual(data["quality"]["mode"], "pending")
        self.assertIn("choices --model", data["next_command"])

    def test_catalog_marks_flare_as_having_ignored_the_requested_size(self):
        entries = json.loads(self.run_cli("catalog").stdout)["models"]
        flare = next(entry for entry in entries if entry["id"] == "gpt-image-2.5-flare")
        self.assertEqual(flare["size_reliability"], "ignored")
        self.assertIn("1536x1024", flare["size_note"])
        self.assertEqual(flare["size"]["verified"], [])

    def test_choices_warns_that_flare_may_ignore_the_requested_size(self):
        data = json.loads(self.run_cli("choices", "--model", "gpt-image-2.5-flare").stdout)
        self.assertEqual(data["size"]["reliability"], "ignored")
        self.assertIn("1536x1024", data["size"]["reliability_note"])
        flare = next(option for option in data["model_options"] if option["id"] == "gpt-image-2.5-flare")
        self.assertEqual(flare["size_reliability"], "ignored")
        self.assertEqual(flare["role"], "风格化；可能忽略尺寸")

    def test_choices_supports_english_labels(self):
        data = json.loads(self.run_cli("choices", "--model", "gpt-image-2", "--lang", "en").stdout)
        self.assertEqual(data["prompt"]["options"][0]["label"], "Original")
        self.assertEqual(data["size"]["options"][0]["orientation_label"], "Square")
        self.assertEqual(data["model_options"][1]["role"], "Exact canvas first")
        self.assertEqual(data["supplement"]["question"], "Additional prompt details (optional)")

    def test_sunburst_publishes_the_twelve_size_menu(self):
        entries = json.loads(self.run_cli("catalog").stdout)["models"]
        profile = next(entry for entry in entries if entry["id"] == "gpt-image-2.5-sunburst")
        self.assertEqual(profile["size"]["mode"], "enum")
        self.assertEqual(profile["size"]["values"], SIZES)
        self.assertEqual(profile["size_reliability"], "documented")

    def test_image_refuses_to_generate_without_an_explicit_selection(self):
        missing_model = self.run_cli("image", "--prompt", "a cat", "--dry-run", unattended=False)
        self.assertNotEqual(missing_model.returncode, 0)
        self.assertIn("missing_selection", missing_model.stderr)
        self.assertIn("--model", missing_model.stderr)

        missing_size_quality = self.run_cli("image", "--model", "gpt-image-2", "--prompt", "a cat", "--dry-run", unattended=False)
        self.assertNotEqual(missing_size_quality.returncode, 0)
        self.assertIn("--size", missing_size_quality.stderr)
        self.assertIn("--quality", missing_size_quality.stderr)

        missing_quality = self.run_cli("image", "--model", "gpt-image-2", "--prompt", "a cat", "--size", "1024x1024", "--dry-run", unattended=False)
        self.assertNotEqual(missing_quality.returncode, 0)
        self.assertIn("--quality", missing_quality.stderr)

        complete = self.run_cli("image", "--model", "gpt-image-2", "--prompt", "a cat", "--size", "1024x1024", "--quality", "high", "--dry-run", unattended=False)
        self.assertEqual(complete.returncode, 0, complete.stderr)

        sunburst = self.run_cli("image", "--model", "gpt-image-2.5-sunburst", "--prompt", "a cat", "--size", "1536x1024", "--quality", "high", "--dry-run", unattended=False)
        self.assertEqual(sunburst.returncode, 0, sunburst.stderr)
        self.assertEqual(json.loads(sunburst.stdout)["body"]["size"], "1536x1024")

    def test_valid_size_and_quality_reach_the_request(self):
        body = self.body("image", "--model", "gpt-image-2", "--prompt", "a cat", "--size", "1536x1024", "--quality", "high")
        self.assertEqual(body["size"], "1536x1024")
        self.assertEqual(body["quality"], "high")

    def test_unlisted_size_is_rejected_with_the_allowed_values(self):
        self.rejects("1024x1024, 1536x1024", "image", "--model", "gpt-image-2", "--prompt", "a cat", "--size", "512x512")

    def test_large_sizes_are_offered_and_carry_a_verified_list(self):
        entries = json.loads(self.run_cli("catalog").stdout)["models"]
        profile = next(entry for entry in entries if entry["id"] == "gpt-image-2")
        self.assertIn("3840x2160", profile["size"]["values"])
        self.assertIsInstance(profile["size"]["verified"], list)

    def test_unlisted_quality_is_rejected_with_the_allowed_values(self):
        self.rejects("auto, low, medium, high", "image", "--model", "gpt-image-2", "--prompt", "a cat", "--quality", "ultra")

    def test_sunburst_accepts_and_sends_a_size(self):
        body = self.body("image", "--model", "gpt-image-2.5-sunburst", "--prompt", "a cat", "--size", "1536x1024", "--quality", "high")
        self.assertEqual(body["size"], "1536x1024")
        self.assertEqual(body["quality"], "high")

    def test_unknown_model_requires_the_escape_hatch_for_options(self):
        self.rejects("--allow-unverified", "image", "--model", "acme/custom", "--prompt", "a cat", "--size", "1024x1024")

    def test_unknown_model_still_passes_through_without_options(self):
        body = self.body("image", "--model", "acme/custom", "--prompt", "a cat")
        self.assertEqual(body["model"], "acme/custom")
        self.assertNotIn("size", body)

    def test_escape_hatch_sends_raw_values(self):
        body = self.body("image", "--model", "acme/custom", "--prompt", "a cat", "--size", "777x777", "--allow-unverified")
        self.assertEqual(body["size"], "777x777")

    def test_alias_resolves_before_the_catalog_lookup(self):
        body = self.body("image", "--model", "image2", "--prompt", "a cat", "--quality", "medium")
        self.assertEqual(body["model"], "gpt-image-2")
        self.assertEqual(body["quality"], "medium")

    def test_doctor_reports_catalog_models_and_menu_version(self):
        process = self.run_cli("doctor")
        self.assertEqual(process.returncode, 0, process.stderr)
        data = json.loads(process.stdout)
        self.assertIn("gpt-image-2", data["catalog_models"])
        self.assertEqual(data["menu_version"], "2026-10-24.4")

    def generate(self, *args):
        with relay(lambda request: reply_json({"data": [{"b64_json": base64.b64encode(PNG).decode()}]})) as (base, requests):
            with tempfile.TemporaryDirectory(prefix="relay-catalog-tests-") as output:
                process = self.run_cli(*args, "--output-dir", output, base=base)
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertEqual(len(requests), 1)
                return json.loads(process.stdout)

    def test_result_reports_the_delivered_canvas_and_warns_on_a_mismatch(self):
        result = self.generate("image", "--model", "gpt-image-2", "--prompt", "a cat", "--size", "1024x1024")
        self.assertEqual(result["sizes"], ["1x1"])
        self.assertIn("1024x1024", result["warnings"][0])
        self.assertIn("1x1", result["warnings"][0])

    def test_sunburst_warns_when_the_canvas_differs(self):
        result = self.generate("image", "--model", "gpt-image-2.5-sunburst", "--prompt", "a cat", "--size", "1536x1024")
        self.assertEqual(result["sizes"], ["1x1"])
        self.assertIn("1536x1024", result["warnings"][0])

    def test_no_warning_when_nothing_was_requested(self):
        result = self.generate("image", "--model", "gpt-image-2", "--prompt", "a cat")
        self.assertEqual(result["sizes"], ["1x1"])
        self.assertNotIn("warnings", result)

    def test_jpeg_output_reports_its_canvas(self):
        with relay(lambda request: reply_json({"data": [{"b64_json": base64.b64encode(JPEG).decode()}]})) as (base, requests):
            with tempfile.TemporaryDirectory(prefix="relay-catalog-tests-") as output:
                process = self.run_cli("image", "--model", "gpt-image-2", "--prompt", "a cat", "--size", "1024x1024", "--output-dir", output, base=base)
                self.assertEqual(process.returncode, 0, process.stderr)
                result = json.loads(process.stdout)
                self.assertEqual(result["sizes"], ["1024x1024"])
                self.assertNotIn("warnings", result)

    def test_non_png_output_skips_size_reporting_instead_of_crashing(self):
        with relay(lambda request: reply_json({"data": [{"b64_json": base64.b64encode(GIF).decode()}]})) as (base, requests):
            with tempfile.TemporaryDirectory(prefix="relay-catalog-tests-") as output:
                process = self.run_cli("image", "--model", "gpt-image-2", "--prompt", "a cat", "--size", "1024x1024", "--output-dir", output, base=base)
                self.assertEqual(process.returncode, 0, process.stderr)
                result = json.loads(process.stdout)
                self.assertNotIn("sizes", result)
                self.assertNotIn("warnings", result)


if __name__ == "__main__":
    unittest.main()
