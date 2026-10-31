"""Retrieve inspected public text representations of six official census tables.

These are NOT original XLSX workbooks. The manifest pins the text inspected on
2026-10-31; source changes require reviewing a new version, not overwriting it.
python scripts/krasnodar_census_sources.py --output /tmp/krasnodar-census
"""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = Path(__file__).resolve().parents[1] / "research_context/krasnodar_agglomeration/comparison/census_sources.json"
    for row in json.loads(manifest.read_text()):
        with urlopen(row["reader_url"], timeout=55) as response:
            data = response.read()
        observed = hashlib.sha256(data).hexdigest()
        if observed != row["extraction_sha256"]:
            raise ValueError(f"Changed extraction for {row['url']}; inspect headers and content before use")
        (args.output / row["extraction_file"]).write_bytes(data)
        print(row["extraction_file"], len(data), "bytes; matches inspected extraction")


if __name__ == "__main__":
    main()
