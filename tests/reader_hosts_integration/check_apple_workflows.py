"""Actions-only check that common-source entry preserves every Apple suite."""
import copy
import os
from pathlib import Path
import subprocess

import yaml

ORIGINAL = '2c5a6cbb087c43abd7643e0085b3300fde95f125'
WORKFLOWS = ('reader-apple-reading-records', 'reader-apple-navigation',
             'reader-apple-search', 'reader-apple-shelf',
             'reader-apple-import-mapping', 'wp13-apple')
COMMON = 'codex/reader-hosts-integration'


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    for name in WORKFLOWS:
        path = '.github/workflows/' + name + '.yml'
        original = yaml.load(subprocess.check_output(
            ['git', 'show', ORIGINAL + ':' + path], text=True), Loader=yaml.BaseLoader)
        current = yaml.load(Path(path).read_text(), Loader=yaml.BaseLoader)
        restored = copy.deepcopy(current)
        steps = restored['jobs']['sdk']['steps']
        added = [s for s in steps if s.get('name') == 'Authenticate exact common-source host merge']
        assert len(added) == 1 and added[0] == {
            'name': 'Authenticate exact common-source host merge',
            'if': "github.ref_name == '" + COMMON + "'",
            'run': 'python3 tests/reader_hosts_integration/guard.py'}, path
        index = steps.index(added[0])
        assert steps[index + 1].pop('if') == "github.ref_name != '" + COMMON + "'", path
        steps.remove(added[0])
        checkout = steps[0]
        assert checkout.get('uses') == 'actions/checkout@v4', path
        assert checkout.get('with', {}).get('fetch-depth') == '0', path
        if name == 'wp13-apple':
            assert checkout.pop('with') == {'fetch-depth': '0'}, path
        assert restored == original, 'Apple suite changed beyond the exact common-source guard: ' + path
    print('All six original Apple workflows preserved; common-source SDK lineage guard added')


if __name__ == '__main__':
    main()
