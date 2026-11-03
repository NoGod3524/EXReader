"""Run the real Mach-O positive and deliberately embedded-implementation controls."""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from check_apple_product import inspect


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--prefix', type=Path, required=True)
    p.add_argument('--consumer', type=Path, required=True)
    p.add_argument('--map', type=Path, required=True)
    p.add_argument('--sqlite-source', type=Path, required=True)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if sys.platform != 'darwin':
        p.error('Real Apple controls require an Apple host')
    args.output.mkdir(parents=True, exist_ok=True)
    metadata = json.loads((args.prefix / 'share/exreader-sqlite/provider.json').read_text())
    provider = args.prefix / metadata['runtime_library']
    sdk = args.prefix / 'lib/libexreader.dylib'
    positive = inspect(args.consumer, args.map, shared_provider=provider, shared_sdk=sdk)
    (args.output / 'apple-positive.json').write_text(json.dumps(positive, indent=2), encoding='utf-8')
    for role, image in [('consumer', args.consumer), ('sdk', sdk), ('provider', provider)]:
        for tool, argv in [('nm', ['nm', str(image)]), ('dependencies', ['otool', '-L', str(image)])]:
            (args.output / (role + '-' + tool + '.txt')).write_text(
                subprocess.check_output(argv, text=True), encoding='utf-8')
    subprocess.run(['cmake', '-S', str(Path(__file__).parent), '-B', str(args.build),
        '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_PREFIX_PATH=' + str(args.prefix),
        '-DSQLITE_SOURCE_DIR=' + str(args.sqlite_source), '-DPROVIDER_PREFIX=' + str(args.prefix)], check=True)
    subprocess.run(['cmake', '--build', str(args.build), '--parallel', '3'], check=True)
    sdk_mutants = list((args.build / 'bad-sdk').glob('libexreader.*.*.dylib'))
    if len(sdk_mutants) != 1:
        raise RuntimeError('Expected one actual SDK mutant image')
    cases = [('main_embedded', args.build / 'embedded_main', args.build / 'embedded-main.map', sdk,
              'main embeds a second SQLite implementation'),
             ('sdk_embedded', args.consumer, args.map, sdk_mutants[0],
              'sdk embeds a second SQLite implementation')]
    results = []
    for name, binary, mapping, sdk_image, required_error in cases:
        transcript = io.StringIO()
        try:
            with contextlib.redirect_stdout(transcript):
                inspect(binary, mapping, shared_provider=provider, shared_sdk=sdk_image)
        except AssertionError as exc:
            if required_error not in str(exc):
                raise RuntimeError(name + ' failed for a different reason: ' + str(exc)) from exc
            results.append({'name': name, 'rejected': True, 'error': str(exc),
                'main_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
                'sdk_sha256': hashlib.sha256(sdk_image.read_bytes()).hexdigest()})
            (args.output / (name + '.log')).write_text(transcript.getvalue() + '\n' + str(exc), encoding='utf-8')
        else:
            raise RuntimeError('Accepted the real embedded-SQLite mutant: ' + name)
    (args.output / 'apple-real-negatives.json').write_text(json.dumps({
        'acceptance_assessed': False, 'controls': results, 'passed': len(results), 'total': 2}, indent=2), encoding='utf-8')
    print('Real Apple embedded-implementation controls rejected: 2/2')


if __name__ == '__main__':
    main()
