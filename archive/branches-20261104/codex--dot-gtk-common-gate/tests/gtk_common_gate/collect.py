"""Bind current common-source admission to the unchanged D26 runtime authenticator."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import guard


def main():
    # Original authenticator runs with all original arguments and assertions.
    subprocess.run([sys.executable, str(guard.ROOT / 'tests/reader_d26_accessibility/identity_current.py'),
                    *sys.argv[1:]], cwd=guard.ROOT, check=True)
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args, _ = parser.parse_known_args()
    report = json.loads(args.output.read_text())
    assert report['current_verified'] is True and report['problems'] == []
    expected = guard.inspect()
    proofs = list(args.artifact.rglob('gtk-common-source.json'))
    assert len(proofs) == 1, 'Source admission missing or duplicated in original producer ZIP'
    actual = json.loads(proofs[0].read_text())
    assert actual == expected, 'Producer and collector source admission differ'
    report['common_source_admission'] = actual
    report['common_source_admission_sha256'] = hashlib.sha256(proofs[0].read_bytes()).hexdigest()
    report['common_source_verified'] = True
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
