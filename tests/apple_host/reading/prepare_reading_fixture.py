# SPDX-License-Identifier: MIT
"""Write actual reading originals only inside Actions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import zipfile


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Actions only')
    parser = argparse.ArgumentParser()
    parser.add_argument('--resources', type=Path, required=True)
    args = parser.parse_args()
    text = '\n\n'.join('Reading paragraph %04d. Unique native bookmark, café 中文 😀 and retained annotation.' % i
                         for i in range(400))
    (args.resources / 'Records.txt').write_text(text, encoding='utf-8')
    with zipfile.ZipFile(args.resources / 'NavigationPages.cbz') as source:
        image = source.read(source.namelist()[0])
    with zipfile.ZipFile(args.resources / 'UnicodePages.cbz', 'w', compression=zipfile.ZIP_DEFLATED) as target:
        for name in ('café.png', 'cafe\u0301.png'):
            target.writestr(name, image)
    manifest = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(args.resources.iterdir()) if path.is_file() and path.name != 'manifest.json'}
    (args.resources / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    print(json.dumps(manifest, sort_keys=True))


if __name__ == '__main__':
    main()
