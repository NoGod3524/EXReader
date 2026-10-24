# SPDX-License-Identifier: MIT
"""Compile the native Apple host with its installed product dependencies."""
import argparse
from pathlib import Path
import subprocess
from check_apple_product import inspect
import json


LIBRARIES = ('reader_session', 'reader_sync', 'exr_webdav', 'reader_commands',
             'reader_reading_state_codec', 'reader_revisions', 'reader_revision_hash',
             'reader_catalog', 'reader_catalog_sqlite', 'exr_credentials')


def flags(sdk):
    sdk = Path(sdk).absolute()
    module = Path(__file__).absolute().parents[1] / 'examples/apple/product'
    includes = (sdk / 'include', sdk / 'include/exreader-product', module)
    archives = [sdk / 'lib' / ('lib' + name + '.a') for name in LIBRARIES]
    for path in [*includes, *archives]:
        if not path.exists():
            raise RuntimeError('Missing installed Apple product dependency: ' + str(path))
    result = [item for path in includes for item in ('-I', str(path))]
    result += [str(path) for path in archives]
    result += ['-lc++', '-lxml2', '-framework', 'Foundation', '-framework', 'CoreFoundation',
               '-framework', 'Security']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    arguments = args.arguments[1:] if args.arguments[:1] == ['--'] else args.arguments
    output = Path(arguments[arguments.index('-o') + 1])
    mapping = Path(str(output) + '.link.map')
    subprocess.run(['xcrun', 'swiftc', *arguments, *flags(args.sdk), '-Xlinker', '-map',
                    '-Xlinker', str(mapping)], check=True)
    Path(str(output) + '.product.json').write_text(json.dumps(inspect(output, mapping), indent=2) + '\n')


if __name__ == '__main__':
    main()
