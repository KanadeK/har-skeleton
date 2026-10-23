import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from examples.demo import capture
from har_skeleton.core import HarError, build_skeleton, load_har, write_new


class SkeletonTests(unittest.TestCase):
    def setUp(self):
        self.raw = capture()

    def test_preserves_performance_and_does_not_mutate(self):
        before = copy.deepcopy(self.raw)
        output, counts = build_skeleton(self.raw)
        self.assertEqual(self.raw, before)
        entry = output["log"]["entries"][0]
        self.assertEqual(entry["time"], 120)
        self.assertEqual(entry["response"]["content"]["size"], 42)
        self.assertEqual(entry["timings"]["wait"], 100)
        self.assertEqual(counts, {"entries": 1, "pages": 0, "origins": 1, "endpoints": 1})

    def test_canaries_in_every_untrusted_text_channel_are_removed(self):
        entry = self.raw["log"]["entries"][0]
        secret = "UNIQUE_PRIVATE_CANARY"
        self.raw["log"].update(
            {"comment": secret, "browser": {"name": secret}, "_extension": secret}
        )
        entry.update(
            {
                "serverIPAddress": secret,
                "connection": secret,
                "comment": secret,
                "_webSocketMessages": [{"data": secret}],
            }
        )
        entry["request"].update(
            {
                "url": f"https://{secret}:{secret}@{secret}.invalid/{secret}?{secret}={secret}#{secret}",
                "method": secret,
                "httpVersion": secret,
                "headers": [{"name": secret, "value": secret}],
                "cookies": [{"name": secret, "value": secret}],
                "queryString": [{"name": secret, "value": secret}],
                "postData": {"text": secret, "params": [{"name": secret, "value": secret}]},
            }
        )
        entry["response"].update(
            {
                "statusText": secret,
                "redirectURL": secret,
                "httpVersion": secret,
                "headers": [{"name": secret, "value": secret}],
                "cookies": [{"name": secret, "value": secret}],
                "content": {
                    "size": 42,
                    "mimeType": secret,
                    "text": secret,
                    "encoding": secret,
                    "_vendor": secret,
                },
            }
        )
        entry["cache"] = {"beforeRequest": {"eTag": secret}}
        output, _ = build_skeleton(self.raw)
        text = json.dumps(output)
        self.assertNotIn(secret, text)
        self.assertNotIn("DEMO_SECRET", text)
        self.assertNotIn("2026-01-02", text)

    def test_aliases_preserve_origin_and_path_correlation(self):
        first = self.raw["log"]["entries"][0]
        for url in [
            "https://demo.invalid/private-user?other=2",
            "https://demo.invalid/another",
            "https://second.invalid/private-user",
        ]:
            other = copy.deepcopy(first)
            other["request"]["url"] = url
            self.raw["log"]["entries"].append(other)
        output, counts = build_skeleton(self.raw)
        urls = [entry["request"]["url"] for entry in output["log"]["entries"]]
        self.assertEqual(urls[0], urls[1])
        self.assertNotEqual(urls[0], urls[2])
        self.assertIn("host-2.invalid", urls[3])
        self.assertEqual(counts["endpoints"], 3)

    def test_timestamps_pages_and_relative_offsets(self):
        log = self.raw["log"]
        log["pages"] = [
            {
                "id": "private-id",
                "title": "private-title",
                "startedDateTime": "2026-01-02T11:59:59+02:00",
                "pageTimings": {"onLoad": 120, "comment": "private"},
            }
        ]
        log["entries"][0]["pageref"] = "private-id"
        second = copy.deepcopy(log["entries"][0])
        second["startedDateTime"] = "2026-01-02T10:00:00.250Z"
        log["entries"].append(second)
        output, _ = build_skeleton(self.raw)
        entries = output["log"]["entries"]
        self.assertEqual(
            output["log"]["pages"][0]["startedDateTime"], "2000-01-01T00:00:00.000000Z"
        )
        self.assertEqual(entries[0]["startedDateTime"], "2000-01-01T00:00:01.000000Z")
        self.assertEqual(entries[1]["startedDateTime"], "2000-01-01T00:00:01.250000Z")
        self.assertEqual(entries[0]["pageref"], "page-1")
        self.assertNotIn("private", json.dumps(output))

    def test_duplicate_page_ids_and_dangling_reference_rejected(self):
        self.raw["log"]["entries"][0]["pageref"] = "missing"
        with self.assertRaises(HarError):
            build_skeleton(self.raw)
        self.raw["log"]["pages"] = [{"id": "one", "startedDateTime": "2026-01-02T10:00:00Z"}] * 2
        with self.assertRaises(HarError):
            build_skeleton(self.raw)

    def test_empty_capture(self):
        output, counts = build_skeleton({"log": {"entries": []}})
        self.assertEqual(output["log"]["entries"], [])
        self.assertEqual(counts["origins"], 0)

    def test_mime_allowlist_discards_parameters_and_unknown_values(self):
        content = self.raw["log"]["entries"][0]["response"]["content"]
        for mime, expected in [
            ("APPLICATION/JSON; boundary=PRIVATE", "application/json"),
            ("image/PRIVATE", "application/octet-stream"),
            ([], "application/octet-stream"),
        ]:
            with self.subTest(mime=mime):
                content["mimeType"] = mime
                output, _ = build_skeleton(self.raw)
                self.assertEqual(
                    output["log"]["entries"][0]["response"]["content"]["mimeType"], expected
                )

    def test_numeric_edges(self):
        for invalid in [True, "private", float("nan"), float("inf"), -2, 10**500, {}, None]:
            with self.subTest(invalid=type(invalid).__name__):
                self.raw["log"]["entries"][0]["time"] = invalid
                with self.assertRaises(HarError):
                    build_skeleton(self.raw)

    def test_fractional_sizes_and_invalid_status_rejected(self):
        for field, value in [
            ("status", 1000),
            ("status", -1),
            ("status", 200.5),
            ("bodySize", 2.5),
        ]:
            raw = capture()
            raw["log"]["entries"][0]["response"][field] = value
            with self.assertRaises(HarError):
                build_skeleton(raw)

    def test_bad_structure(self):
        for raw in [
            None,
            [],
            {},
            {"log": []},
            {"log": {"entries": {}}},
            {"log": {"entries": ["private"]}},
        ]:
            with self.subTest(raw=raw), self.assertRaises(HarError):
                build_skeleton(raw)

    def test_bad_urls_do_not_echo_values(self):
        for url in [
            "file:///PRIVATE",
            "https://PRIVATE:bad/private",
            "//PRIVATE",
            "data:PRIVATE",
            None,
            [],
        ]:
            self.raw["log"]["entries"][0]["request"]["url"] = url
            with self.subTest(url=url), self.assertRaises(HarError) as context:
                build_skeleton(self.raw)
            self.assertNotIn("PRIVATE", str(context.exception))

    def test_bad_date_and_excessive_span(self):
        for date in ["PRIVATE", "2026-01-01T00:00:00", None, "9999-99-99Z"]:
            self.raw["log"]["entries"][0]["startedDateTime"] = date
            with self.assertRaises(HarError):
                build_skeleton(self.raw)
        self.raw = capture()
        second = copy.deepcopy(self.raw["log"]["entries"][0])
        second["startedDateTime"] = "2028-01-01T00:00:00Z"
        self.raw["log"]["entries"].append(second)
        with self.assertRaises(HarError):
            build_skeleton(self.raw)

    def test_entry_limit(self):
        self.raw["log"]["entries"] *= 2
        with self.assertRaises(HarError):
            build_skeleton(self.raw, max_entries=1)


class FileAndCliTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "source.har"
        self.output = self.root / "output.har"
        self.source.write_text(json.dumps(capture()), encoding="utf-8")

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "har_skeleton", *map(str, args)], capture_output=True, text=True
        )

    def test_cli_core_flow(self):
        original = self.source.read_bytes()
        result = self.run_cli(self.source, self.output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["entries"], 1)
        self.assertNotIn("DEMO_SECRET", self.output.read_text(encoding="utf-8"))
        self.assertEqual(self.source.read_bytes(), original)

    def test_existing_output_and_same_input_refused(self):
        self.output.write_text("KEEP", encoding="utf-8")
        self.assertEqual(self.run_cli(self.source, self.output).returncode, 2)
        self.assertEqual(self.output.read_text(encoding="utf-8"), "KEEP")
        before = self.source.read_bytes()
        self.assertEqual(self.run_cli(self.source, self.source).returncode, 2)
        self.assertEqual(self.source.read_bytes(), before)

    def test_dangling_symlink_refused_when_supported(self):
        try:
            self.output.symlink_to(self.root / "missing")
        except OSError:
            self.skipTest("symlink creation requires OS privileges")
        self.assertEqual(self.run_cli(self.source, self.output).returncode, 2)
        self.assertFalse((self.root / "missing").exists())

    def test_bom_supported(self):
        self.source.write_bytes(b"\xef\xbb\xbf" + json.dumps(capture()).encode())
        self.assertIn("log", load_har(self.source))

    def test_duplicate_keys_nan_bad_encoding_and_json(self):
        for data in [b'{"log":{},"log":{}}', b'{"n":NaN}', b"\xff", b'{"PRIVATE":']:
            self.source.write_bytes(data)
            result = self.run_cli(self.source, self.output)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("PRIVATE", result.stderr)
            self.assertFalse(self.output.exists())

    def test_input_byte_limit(self):
        with self.assertRaises(HarError):
            load_har(self.source, max_bytes=1)
        self.assertEqual(self.run_cli(self.source, self.output, "--max-bytes", "1").returncode, 2)
        self.assertFalse(self.output.exists())

    def test_missing_file_error_does_not_leak_path(self):
        result = self.run_cli(self.root / "PRIVATE.har", self.output)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("PRIVATE", result.stderr)

    def test_output_is_utf8_json(self):
        output, _ = build_skeleton(capture())
        write_new(self.output, output)
        self.assertEqual(load_har(self.output), output)


if __name__ == "__main__":
    unittest.main()
