"""Three-linker extension of the original codec consumer's isolation check."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reader_module_composition'))
from check_composition import archive_providers, direct_providers


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    parser = argparse.ArgumentParser()
    for name in ('consumer', 'map', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True)
    done = subprocess.run([str(args.consumer.resolve())], capture_output=True, text=True, timeout=30)
    (args.output / 'consumer.log').write_text(done.stdout + '\n' + done.stderr)
    assert done.returncode == 0 and 'no SDK linked' in done.stdout
    text = args.map.read_text(errors='replace')
    # G08 already handles GNU ld, MSVC and ld64, unlike the old two-OS
    # reader_reading_state/check_reading_state.sqlite_providers helper.
    providers = archive_providers(text)
    assert len(providers) == 1 and 'reader_catalog_sqlite' in providers[0], providers
    assert not direct_providers(text), 'directly linked amalgamation'
    assert not re.search(r'\bexr_(?:anchor|library|pager|fixed|publication|document)_\w+', text)
    assert 'exr_vendor_exr_sqlite' not in text
    report = dict(accepted=True, sdk_symbols=False, sqlite_providers=providers,
                  source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                  attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                  consumer_sha256=hashlib.sha256(args.consumer.read_bytes()).hexdigest(),
                  map_sha256=hashlib.sha256(args.map.read_bytes()).hexdigest())
    (args.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
