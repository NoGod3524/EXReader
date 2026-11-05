"""Authenticate all bundle bytes; distinguish transport metadata from producer facts."""
import hashlib
import json
from pathlib import Path
import stat
import app_bundle
from identity import require, SOURCE, RUN, ATTEMPT


def snapshot(app):
    app = Path(app)
    files, links, special = app_bundle.walk(app)
    require(not special, 'bundle contains special files')
    for row in links:
        path = app / row['path']
        require(not row['absolute'] and not row['escapes'] and
                path.resolve().is_relative_to(app.resolve()), 'bundle symlink escapes its root')
    directories = [{'path': '.', 'mode': oct(stat.S_IMODE(app.stat().st_mode))}]
    for path in sorted(app.rglob('*')):
        if path.is_dir() and not path.is_symlink():
            directories.append(dict(path=path.relative_to(app).as_posix(), mode=oct(stat.S_IMODE(path.stat().st_mode))))
    content = {row['path']: dict(bytes=row['bytes'], sha256=row['sha256']) for row in files}
    return dict(content=content, files=sorted(files, key=lambda row: row['path']),
                links=sorted(links, key=lambda row: row['path']), directories=directories)


def same(actual, expected, include_metadata=True):
    require(actual['content'] == expected['content'], 'bundle file set/bytes/hash changed')
    require(actual['links'] == expected['links'], 'observed bundle links changed')
    if include_metadata:
        require(actual['files'] == expected['files'] and actual['directories'] == expected['directories'],
                'observed staged/tar bundle modes changed')


def authenticate_original(extraction, app, platform):
    extraction, app = Path(extraction), Path(app)
    report_bytes = (extraction / 'result.json').read_bytes()
    require(len(report_bytes) <= 16 * 1024**2, 'original producer report too large')
    report = json.loads(report_bytes)
    require(report['accepted'] and (report['source_sha'], str(report['run_id']), str(report['attempt']), report['platform']) ==
            (SOURCE, str(RUN), str(ATTEMPT), platform), 'original producer report identity differs')
    require(app.relative_to(extraction).as_posix() == 'program-raw/EXReaderHost.app', 'wrong actual raw app directory')
    prefix = 'program-raw/EXReaderHost.app/'
    declared = {name[len(prefix):]: row for name, row in report['files'].items() if name.startswith(prefix)}
    observed = snapshot(app)
    # Original raw producer inventoried ordinary file bytes, but did not attest
    # chmod values or symlink targets. The artifact ZIP cannot fill that gap.
    require(observed['content'] == declared and declared, 'bundle bytes differ from original report inventory')
    require(not observed['links'], 'source report cannot authenticate original symlink targets')
    phases = [row for row in report['phases'] if row['mode'] == 'raw']
    executable = app / 'EXReaderHost'
    program_sha = app_bundle.sha256(executable)
    require(phases and all(row['app_sha256'] == row['provider']['binary_sha256'] == program_sha for row in phases),
            'actual raw executable differs from successful phase programs')
    return dict(original_report_sha256=hashlib.sha256(report_bytes).hexdigest(),
                original_bundle_bytes_authenticated=True, snapshot=observed,
                original_modes_links_accepted=False, original_modes_links_status='pending',
                original_modes_links_reason='original report has bytes/hashes only; Actions ZIP is not an original mode/link attestation')


def installed_facts(source, installed):
    before, after = snapshot(source), snapshot(installed)
    same(after, before, include_metadata=False)
    return dict(all_bundle_bytes_match=True, all_observed_links_match=True,
                observed_modes_match=before['files'] == after['files'] and before['directories'] == after['directories'],
                source_snapshot=before, installed_snapshot=after,
                original_modes_links_accepted=False, original_modes_links_status='pending')


def running_program(pid, ps_output, executable):
    fields = ps_output.strip().split(None, 1)
    return len(fields) == 2 and fields[0] == str(pid) and Path(fields[1]).resolve() == Path(executable).resolve()
