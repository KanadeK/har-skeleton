"""Generate synthetic data, invoke the installed CLI and verify a real output file."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def capture() -> dict:
    return {
        "log": {
            "version": "1.2",
            "entries": [
                {
                    "startedDateTime": "2026-01-02T10:00:00Z",
                    "time": 120,
                    "request": {
                        "method": "GET",
                        "url": "https://demo.invalid/private-user?token=DEMO_SECRET",
                        "headers": [{"name": "Authorization", "value": "DEMO_SECRET"}],
                    },
                    "response": {
                        "status": 200,
                        "content": {
                            "size": 42,
                            "mimeType": "application/json",
                            "text": "DEMO_SECRET",
                        },
                    },
                    "timings": {"send": 1, "wait": 100, "receive": 19},
                    "_unknown": {"private": "DEMO_SECRET"},
                }
            ],
        }
    }


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source, output = root / "input.har", root / "share.har"
        source.write_text(json.dumps(capture()), encoding="utf-8")
        subprocess.run([sys.executable, "-m", "har_skeleton", str(source), str(output)], check=True)
        text = output.read_text(encoding="utf-8")
        assert "DEMO_SECRET" not in text and "private-user" not in text
        entry = json.loads(text)["log"]["entries"][0]
        assert entry["time"] == 120 and entry["response"]["status"] == 200
        print("PASS: original text removed; timing and status preserved; temporary files cleaned.")


if __name__ == "__main__":
    main()
