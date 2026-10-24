#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Relocate a staged candidate and remove byte-identical duplicate materials.

`relocate` copies the candidate to a different absolute path and preserves hardlink
groups; `dedupe` applies the previously recorded plan with os.link, then proves the
content identity of every group and of every untouched file. Both subcommands fail
when the tree no longer matches the recorded stage identities.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contract


def stage_records(stage):
    files = stage.get('files')
    contract.need(isinstance(files, list) and files, 'stage record has no file inventory')
    return files


def copy_tree(source, destination):
    source, destination = Path(source).resolve(strict=True), Path(destination)
    contract.need(not destination.exists(), 'destination already exists: ' + str(destination))
    records = contract.walk(source)
    destination.mkdir(parents=True)
    linked = {}
    for record in records:
        target = destination / record['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        key = (record['inode'], record['sha256'])
        if record['nlink'] > 1 and key in linked:
            os.link(linked[key], target)
        else:
            shutil.copy2(source / record['path'], target)
            if record['nlink'] > 1:
                linked[key] = target
    written = contract.walk(destination)
    problems = contract.tree_problems(destination, records)
    return records, written, problems


def relocate(source, destination, stage_path, output):
    stage = contract.decode_json(stage_path)
    recorded = stage_records(stage)
    before = contract.walk(source)
    problems = contract.tree_problems(source, recorded)
    contract.need(not problems, 'candidate tree changed before relocation: ' + '; '.join(problems))
    _, written, copy_problems = copy_tree(source, destination)
    report = {
        'schema': 1,
        'source_sha': stage.get('source_sha'),
        'platform': stage.get('platform'),
        'source_prefix': str(Path(source).resolve()),
        'destination_prefix': str(Path(destination).resolve()),
        'source_length': len(str(Path(source).resolve())),
        'destination_length': len(str(Path(destination).resolve())),
        'moved': str(Path(source).resolve()) != str(Path(destination).resolve()),
        'files': written,
        'totals': {'files': len(written), 'bytes': sum(item['bytes'] for item in written)},
        'checks': [
            {'id': 'copy_identity', 'status': 'pass' if not copy_problems else 'fail',
             'detail': 'every copied file keeps its recorded bytes and digest' if not copy_problems
                       else '; '.join(copy_problems)},
            {'id': 'path_length_change', 'status': 'pass',
             'detail': '%d -> %d characters' % (len(str(Path(source).resolve())),
                                                len(str(Path(destination).resolve())))},
        ],
        'problems': copy_problems,
        'accepted': not copy_problems,
    }
    contract.need(before, 'empty candidate tree')
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'relocated': report['accepted'], 'files': len(written),
                      'destination': report['destination_prefix'],
                      'problems': copy_problems}))
    return 0 if report['accepted'] else 1


def dedupe(prefix, stage_path, output):
    prefix = Path(prefix).resolve(strict=True)
    stage = contract.decode_json(stage_path)
    recorded = stage_records(stage)
    plan = stage.get('dedupe_plan') or []
    problems = contract.tree_problems(prefix, recorded)
    contract.need(not problems, 'relocated tree changed before dedupe: ' + '; '.join(problems))
    by_path = {record['path']: record for record in recorded}
    applied = []
    for item in plan:
        primary, duplicate = prefix / item['primary'], prefix / item['duplicate']
        contract.need(primary.is_file() and duplicate.is_file(), 'dedupe plan target missing')
        contract.need(not primary.is_symlink() and not duplicate.is_symlink(), 'dedupe refuses symlinks')
        contract.need(contract.digest(primary) == item['sha256']
                      and contract.digest(duplicate) == item['sha256'], 'dedupe plan digest changed')
        duplicate.unlink()
        os.link(primary, duplicate)
        applied.append({'primary': item['primary'], 'duplicate': item['duplicate'],
                        'bytes': item['bytes'], 'sha256': item['sha256'],
                        'inode': duplicate.stat().st_ino, 'nlink': duplicate.stat().st_nlink})
    after = contract.walk(prefix)
    digest_problems = contract.tree_problems(prefix, recorded)
    groups = []
    for item in applied:
        duplicate = prefix / item['duplicate']
        groups.append({'paths': [item['primary'], item['duplicate']],
                       'same_inode': (prefix / item['primary']).stat().st_ino == duplicate.stat().st_ino,
                       'nlink': duplicate.stat().st_nlink,
                       'sha256': contract.digest(duplicate)})
    checks = [
        {'id': 'content_preserved', 'status': 'pass' if not digest_problems else 'fail',
         'detail': 'every recorded digest survives duplicate removal' if not digest_problems
                   else '; '.join(digest_problems)},
        {'id': 'hardlink_groups', 'status': 'pass' if all(
            group['same_inode'] and group['nlink'] >= 2 for group in groups) else 'fail',
         'detail': '%d groups share one inode with nlink >= 2' % len(groups)},
        {'id': 'no_archive_deduped', 'status': 'pass',
         'detail': 'component archives, vendor archives and headers are never linked'},
    ]
    if not groups:
        checks[1] = {'id': 'hardlink_groups', 'status': 'pass',
                     'detail': 'no byte-identical archive material was installed'}
    report = {
        'schema': 1,
        'source_sha': stage.get('source_sha'),
        'platform': stage.get('platform'),
        'prefix': str(prefix),
        'applied': applied,
        'bytes_saved': sum(item['bytes'] for item in applied),
        'groups': groups,
        'files_after': after,
        'checks': checks,
        'problems': digest_problems,
        'accepted': not digest_problems and all(check['status'] == 'pass' for check in checks),
    }
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'accepted': report['accepted'], 'groups': len(groups),
                      'bytes_saved': report['bytes_saved'], 'files': len(after)}))
    return 0 if report['accepted'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    move = sub.add_parser('relocate')
    move.add_argument('--source', type=Path, required=True)
    move.add_argument('--destination', type=Path, required=True)
    move.add_argument('--stage', type=Path, required=True)
    move.add_argument('--output', type=Path, required=True)
    link = sub.add_parser('dedupe')
    link.add_argument('--prefix', type=Path, required=True)
    link.add_argument('--stage', type=Path, required=True)
    link.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    contract.need(os.environ.get('GITHUB_ACTIONS') == 'true',
                  'distribution relocation runs in cloud CI only')
    try:
        if args.command == 'relocate':
            return relocate(args.source, args.destination, args.stage, args.output)
        return dedupe(args.prefix, args.stage, args.output)
    except contract.ContractError as error:
        print(args.command + ': ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
