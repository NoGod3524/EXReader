# SPDX-License-Identifier: MIT
"""Actions-only actual GTK executable's installed SQLite provider identity."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reader_reading_state'))
from check_reading_state import sqlite_providers


def main():
    parser = argparse.ArgumentParser()
    for name in ('map', 'binary', 'output'): parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args();assert os.environ.get('GITHUB_ACTIONS') == 'true'
    mapping = args.map.read_text(encoding='utf-8', errors='replace')
    providers = sqlite_providers(mapping)
    assert len(providers) == 1 and 'reader_catalog_sqlite' in providers[0], providers
    assert 'libsqlite3.so' not in mapping and 'winsqlite3' not in mapping
    report = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'providers': providers,
              'map_sha256': hashlib.sha256(args.map.read_bytes()).hexdigest(),
              'program_sha256': hashlib.sha256(args.binary.read_bytes()).hexdigest()}
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8');print(json.dumps(report), flush=True)


if __name__ == '__main__': main()
