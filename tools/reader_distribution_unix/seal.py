#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Seal the deduplicated Unix prefix and re-extract it from the archive bytes.

The archive stores byte-identical materials once as hardlink members; `verify`
reconstructs the tree from those bytes and re-checks every recorded identity.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contract


def seal(args):
    prefix = Path(args.prefix).resolve(strict=True)
    stage = contract.decode_json(args.stage)
    dedupe = contract.decode_json(args.dedupe)
    contract.need(dedupe.get('accepted') is True, 'dedupe report did not accept the tree')
    contract.need(dedupe.get('source_sha') == stage.get('source_sha'), 'dedupe report source differs')
    problems = contract.tree_problems(prefix, stage['files'])
    contract.need(not problems, 'sealed tree changed: ' + '; '.join(problems))
    epoch = int(subprocess.check_output(['git', 'show', '-s', '--format=%ct', 'HEAD'], text=True))
    name = 'EXReader-%s-%s-%s-%s.tar.gz' % (stage['profile'], stage['sdk_version'],
                                            stage['platform'], stage['architecture'])
    identity = {'source_sha': stage['source_sha'], 'ci': stage.get('ci'),
                'platform': stage['platform'], 'runner_os': stage['runner_os'],
                'architecture': stage['architecture'], 'profile': stage['profile'],
                'sdk_version': stage['sdk_version'], 'abi': stage['abi'],
                'pkgconfig_sha256': stage['pkgconfig']['sha256'],
                'dedupe_sha256': contract.digest(args.dedupe), 'epoch': epoch}
    manifest = contract.seal(prefix, args.output, name, epoch, identity)
    manifest['stage_sha256'] = contract.digest(args.stage)
    manifest['duplicate_bytes_retained_once'] = dedupe.get('bytes_saved')
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'archive': manifest['archive'], 'files': len(manifest['files']),
                      'duplicate_members': manifest['duplicate_members']}))
    return 0


def verify(args):
    manifest = contract.decode_json(args.manifest)
    report = contract.extract(args.archive, args.destination, manifest)
    report['manifest_sha256'] = contract.digest(args.manifest)
    report['archive'] = report.get('archive') or manifest.get('archive')
    if report['archive']:
        report['archive']['sha256'] = contract.digest(args.archive)
        report['archive']['bytes'] = Path(args.archive).stat().st_size
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'accepted': report['accepted'], 'members': report['members'],
                      'problems': report['problems']}))
    return 0 if report['accepted'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    write = sub.add_parser('seal')
    write.add_argument('--prefix', type=Path, required=True)
    write.add_argument('--stage', type=Path, required=True)
    write.add_argument('--dedupe', type=Path, required=True)
    write.add_argument('--output', type=Path, required=True)
    check = sub.add_parser('verify')
    check.add_argument('--archive', type=Path, required=True)
    check.add_argument('--manifest', type=Path, required=True)
    check.add_argument('--destination', type=Path, required=True)
    check.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    contract.need(os.environ.get('GITHUB_ACTIONS') == 'true',
                  'distribution archives are sealed in cloud CI only')
    try:
        return seal(args) if args.command == 'seal' else verify(args)
    except contract.ContractError as error:
        print(args.command + ': ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
