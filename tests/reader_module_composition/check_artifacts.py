# SPDX-License-Identifier: MIT
"""Strict same-source aggregate for the module composition gate (Actions only).

Each platform producer uploads its own summaries. This checker authenticates
the ZIPs of this exact run and attempt, binds every summary to this source and
attempt, and refuses a missing platform, a failed platform, a foreign source, a
duplicate name, a mismatched SQLite provider count or an empty install manifest.
"""
import hashlib
import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_parallel_integration import download_artifact_zip, fetch, pages, require

PLATFORMS = [('linux', 'Linux'), ('windows', 'Windows'), ('macos', 'macOS')]
WORKFLOW = '.github/workflows/reader-module-composition.yml'


def verify_bundles(bundles, source, run_id, attempt):
    """Return the list of problems for a set of per-platform summaries."""
    problems = []
    seen = set()
    for key, _ in PLATFORMS:
        if key not in bundles:
            problems.append('missing platform ' + key)
            continue
        if key in seen:
            problems.append('duplicate platform ' + key)
            continue
        seen.add(key)
        bundle = bundles[key]
        result = bundle.get('result') or {}
        gates = bundle.get('gates') or {}
        manifest = bundle.get('manifest') or {}
        label = '[' + key + '] '
        if result.get('accepted') is not True:
            problems.append(label + 'composition result not accepted')
        if gates.get('accepted') is not True:
            problems.append(label + 'negative gates not accepted')
        for name, document in (('result', result), ('gates', gates)):
            if str(document.get('source_sha')) != str(source):
                problems.append(label + name + ' source differs')
            if str(document.get('run_id')) != str(run_id):
                problems.append(label + name + ' run id differs')
            if str(document.get('attempt')) != str(attempt):
                problems.append(label + name + ' attempt differs')
        providers = result.get('sqlite_providers') or []
        if len(providers) != 1 or 'reader_catalog_sqlite' not in str(providers[0]):
            problems.append(label + 'product SQLite provider count is ' + str(len(providers)))
        if result.get('direct_providers'):
            problems.append(label + 'links a second amalgamation object')
        if not (result.get('items') and all(item.get('pass') for item in result['items'])):
            problems.append(label + 'has no accepted composition items')
        if not (gates.get('items') and all(item.get('pass') for item in gates['items'])):
            problems.append(label + 'has no accepted gate items')
        if result.get('resolved_state') != 'FOUND':
            problems.append(label + 'did not resolve on the second SDK')
        if not isinstance(manifest, dict) or not manifest:
            problems.append(label + 'install manifest is empty')
        if result.get('complete_product') is not False or result.get('host_ui_accepted') is not False:
            problems.append(label + 'claims an unearned capability')
    return problems


def self_test():
    good = {}
    for key, _ in PLATFORMS:
        good[key] = {
            'result': {'accepted': True, 'source_sha': 'abc', 'run_id': 1, 'attempt': 2,
                       'sqlite_providers': ['libreader_catalog_sqlite.a'], 'direct_providers': [],
                       'items': [{'name': 'x', 'pass': True}], 'resolved_state': 'FOUND',
                       'complete_product': False, 'host_ui_accepted': False},
            'gates': {'accepted': True, 'source_sha': 'abc', 'run_id': 1, 'attempt': 2,
                      'items': [{'name': 'g', 'pass': True}]},
            'manifest': {'lib/libreader_catalog.a': {'bytes': 1, 'sha256': 'x'}},
        }
    require(not verify_bundles(good, 'abc', 1, 2), 'the control bundle must pass')
    import copy

    def rejected(mutate, name):
        bundle = copy.deepcopy(good)
        mutate(bundle)
        require(verify_bundles(bundle, 'abc', 1, 2), 'the gate accepted ' + name)

    rejected(lambda b: b.pop('macos'), 'a missing platform')
    rejected(lambda b: b['linux']['result'].__setitem__('accepted', False), 'a failing platform')
    rejected(lambda b: b['windows']['result'].__setitem__('source_sha', 'other'), 'a foreign source')
    rejected(lambda b: b['windows']['gates'].__setitem__('attempt', 9), 'a foreign attempt')
    rejected(lambda b: b['macos']['result'].__setitem__(
        'sqlite_providers', ['libreader_catalog_sqlite.a', 'libexr_vendor_exr_sqlite.a']),
        'two SQLite providers')
    rejected(lambda b: b['macos']['result'].__setitem__('direct_providers', ['sqlite3.c.o']),
        'a directly linked amalgamation')
    rejected(lambda b: b['linux'].__setitem__('manifest', {}), 'an empty install manifest')
    rejected(lambda b: b['linux']['result'].__setitem__('resolved_state', 'MISSING'),
             'an unresolved selector')
    rejected(lambda b: b['linux']['result'].__setitem__('complete_product', True),
             'an unearned complete-product claim')
    print('rejection self-test passed: %d negative controls' % 9)


def main():
    arguments = sys.argv[1:]
    if '--self-test' in arguments:
        require(os.environ.get('GITHUB_ACTIONS') == 'true', 'cloud only')
        self_test()
        return 0
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'cloud only')
    downloads = Path(arguments[arguments.index('--downloads') + 1]).resolve()
    output = Path(arguments[arguments.index('--output') + 1]).resolve()
    downloads.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    source = os.environ['GITHUB_SHA']
    run_id, attempt = int(os.environ['GITHUB_RUN_ID']), int(os.environ['GITHUB_RUN_ATTEMPT'])
    summary = {'accepted': False, 'source_sha': source, 'run_id': run_id, 'attempt': attempt,
               'artifacts': [], 'problems': [], 'platforms': {}, 'host_ui_accepted': False,
               'android_accepted': False, 'ios_accepted': False, 'complete_product': False,
               'scope': 'Windows, Linux and macOS installed-prefix composition on this source'}
    try:
        run = fetch('actions/runs/%d' % run_id)
        require(run['head_sha'] == source and run['run_attempt'] == attempt and
                run['path'] == WORKFLOW, 'caller identity differs')
        artifacts = pages('actions/runs/%d/artifacts' % run_id, 'artifacts')
        jobs = pages('actions/runs/%d/attempts/%d/jobs' % (run_id, attempt), 'jobs')
        bundles = {}
        for key, runner in PLATFORMS:
            name = 'reader-module-composition-%s-%d-%d' % (key, run_id, attempt)
            matches = [artifact for artifact in artifacts if artifact['name'] == name]
            require(len(matches) == 1, 'missing or duplicate artifact ' + name)
            artifact = matches[0]
            job_name = 'one-prefix composition (' + key + ')'
            job_matches = [job for job in jobs if job['name'] == job_name]
            require(len(job_matches) == 1, 'missing or duplicate job ' + job_name)
            job = job_matches[0]
            require(job['head_sha'] == source and job['run_attempt'] == attempt and
                    job['conclusion'] == 'success', 'upstream job failed or differs for ' + key)
            require(not artifact['expired'] and artifact['size_in_bytes'] > 0 and
                    artifact['workflow_run']['head_sha'] == source, 'artifact identity differs for ' + key)
            with tempfile.TemporaryFile() as stream:
                download_artifact_zip(artifact['id'], stream)
                stream.seek(0)
                data = stream.read()
            require(len(data) == artifact['size_in_bytes'] and
                    'sha256:' + hashlib.sha256(data).hexdigest() == artifact['digest'],
                    'ZIP bytes or digest differ for ' + key)
            (downloads / (name + '.zip')).write_bytes(data)
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = archive.namelist()
                # upload-artifact@v4 keeps paths relative to the uploaded root; a
                # different common ancestor only changes the prefix, never the leaf.
                prefix = ''
                for candidate in ('', 'composition/'):
                    if candidate + 'evidence/result.json' in names:
                        prefix = candidate
                        break
                bundle = {}
                for field, relative in (('result', 'evidence/result.json'),
                                        ('gates', 'gates/gates.json'),
                                        ('manifest', 'install-all.json')):
                    with archive.open(prefix + relative) as handle:
                        bundle[field] = json.loads(handle.read())
                bundles[key] = bundle
            summary['artifacts'].append({field: artifact[field] for field in
                                         ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
            summary['platforms'][key] = {
                'runner': runner,
                'items': len(bundle['result'].get('items', [])),
                'gate_items': len(bundle['gates'].get('items', [])),
                'installed_files': len(bundle['manifest']),
                'sqlite_providers': bundle['result'].get('sqlite_providers'),
                'webdav': bundle['result'].get('webdav'),
            }
        problems = verify_bundles(bundles, source, run_id, attempt)
        summary['problems'] = problems
        summary['accepted'] = not problems
    except Exception as error:  # noqa: BLE001 - every failure is recorded, never hidden
        summary['problems'].append(str(error))
    (output / 'result.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary))
    return 0 if summary['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
