# SPDX-License-Identifier: MIT
"""Audit a fixed reader-v1 requirement catalog in Actions; never grant product acceptance."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, pages, download_artifact_zip


def date(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


# Exact, reviewable evidence adapters. They only read retained original artifacts;
# no build, application execution, original result rewriting, or relaxed gates.
F06_RUN = 40678657371
F06_SOURCE = '8f8acf3234cba747165f001c0c96efe1b911e6ad'
F06_PINS = {
    "f06-authenticated": {
        "id": 12812316729,
        "bytes": 2793,
        "sha256": "89cda12bf715d4e8227ecc60b118a8c959452a6e51b51bf4897dddb0cf12a039"
    },
    "sdk342-aggregate": {
        "id": 12812487269,
        "bytes": 1239,
        "sha256": "123f4e5617268a7f50ce01bd8fc97e02cd3024a5a4a663789c458813fb0a76af"
    },
    "f06-windows": {
        "id": 12812276328,
        "bytes": 17696295,
        "sha256": "0206e54988ca50e3feae37d7f83457ab959d052ef350fb55eb9269007c2c9cd2"
    },
    "f06-linux": {
        "id": 12811449234,
        "bytes": 18545727,
        "sha256": "be3a91161939b3b61bce041feaa06679d03120af9f53abea02bab141d5665641"
    },
    "f06-macos": {
        "id": 12811976629,
        "bytes": 27507961,
        "sha256": "f480b2a8489f8b21aa00c795b38fbd4a85261200a654cb2daf6c880bb538b599"
    },
    "f06-android": {
        "id": 12812325830,
        "bytes": 19702584,
        "sha256": "e120fb8a3d73aafb19578aed9d114788177ae104a00f1f754b2cb413c174760e"
    },
    "f06-iphone": {
        "id": 12813015622,
        "bytes": 27511670,
        "sha256": "c56a913aca689f4290a4d66787666e3b22617c39308c3acfc45bd1b3794f3c3b"
    },
    "f06-ipad": {
        "id": 12812242328,
        "bytes": 27511644,
        "sha256": "34cb0a2b9b56f5b6cd4f3347f08505aac3abe128aba59e982cf208e93829acf9"
    }
}
F06_ENTRIES = {
    'windows': 'EXReader/EXReader.exe',
    'linux': 'EXReader-Linux/bin/exreader-linux',
    'macos': 'EXReader.app/Contents/MacOS/EXReader',
    'android': 'artifacts/app-debug.apk',
    'iphone': 'EXReader.app/EXReader',
    'ipad': 'EXReader.app/EXReader',
}
MAC_ORG_RUN = 40635727935
MAC_ORG_SOURCE = '716c1409168960a276e282ce694d32ed82497bc9'
MAC_ORG_PIN = {'id': 12799455200, 'bytes': 4796037,
               'sha256': '1f327fe705f7db3fadbe478f3d54300ce8948928b26ca80865ee17c9dd297417'}
MAC_ORG_PROGRAM = 'c7cdb0875a62a2312dc407051f9ec707e5b19ae7f9dbb46f12a08178c8155ade'
MAC_ORG_CASES = {
    'testGroupLifecycleAndProcessRestart': ['created', 'renamed', 'deleted', 'restored', 'restart'],
    'testMembershipAndProcessRestart': ['imported', 'added', 'restart', 'removed'],
    'testTagAndSeriesPersist': ['tag', 'series', 'restart'],
    'testStagedIntentSurvivesTerminationAndRetry': ['staged', 'reopened', 'retried', 'persisted'],
    'testNestedShelfSurvivesRestart': ['created', 'restart'],
    'testStaleEditDoesNotOverwriteCompetingRevision': ['competing', 'refused', 'preserved'],
}


def evidence_zip(pin, run, source, name):
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'artifact reads are Actions-only'
    item = fetch('actions/artifacts/' + str(pin['id']))
    assert item['id'] == pin['id'] and item['name'] == name
    assert not item['expired'] and date(item['expires_at']) > datetime.now(timezone.utc)
    assert item['workflow_run']['id'] == run and item['workflow_run']['head_sha'] == source
    assert item['size_in_bytes'] == pin['bytes'] and item['digest'] == 'sha256:' + pin['sha256']
    raw = download_artifact_zip(pin['id'])
    assert len(raw) == pin['bytes'] and hashlib.sha256(raw).hexdigest() == pin['sha256']
    return safe_zip(raw)


def safe_zip(raw):
    archive = zipfile.ZipFile(io.BytesIO(raw))
    names = archive.namelist()
    assert len(names) == len(set(names)), 'duplicate ZIP member'
    assert all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts
               and '\\' not in n for n in names), 'unsafe ZIP member'
    return archive


def same_origin(record, source, run):
    assert record['source_sha'] == source
    assert str(record['run_id']) == str(run) and str(record['attempt']) == '1'


def verify_f06(spec, jobs):
    assert spec['adapter'] == 'f06_sdk342_40678657371'
    assert spec['run'] == F06_RUN and spec['source_prefix'] == F06_SOURCE
    assert len(jobs) == 12 and all(job['conclusion'] == 'success' for job in jobs)
    def original(name):
        return evidence_zip(F06_PINS[name], F06_RUN, F06_SOURCE, name + '-40678657371-1')
    with original('f06-authenticated') as archive:
        six = json.loads(archive.read('summary.json'))
    same_origin(six, F06_SOURCE, F06_RUN)
    assert six['accepted'] is True and six['failures'] == []
    assert set(six['targets']) == set(F06_ENTRIES)
    with original('sdk342-aggregate') as archive:
        aggregate = json.loads(archive.read('summary.json'))
    same_origin(aggregate, F06_SOURCE, F06_RUN)
    assert aggregate['accepted'] is True and aggregate['failures'] == []
    assert aggregate['checks']['original_six_target_f06'] is True
    assert aggregate['checks']['five_gates_authenticated'] is True
    programs = {}
    for target, entry_path in F06_ENTRIES.items():
        name = 'f06-' + target
        proof = six['targets'][target]
        pin = F06_PINS[name]
        assert proof['github_artifact_id'] == pin['id']
        assert proof['github_artifact_digest'] == 'sha256:' + pin['sha256']
        aggregate_pin = aggregate['artifacts'][name + '-40678657371-1']
        assert aggregate_pin['id'] == pin['id'] and aggregate_pin['sha256'] == pin['sha256']
        with original(name) as archive:
            result = json.loads(archive.read('result.json'))
            assert result == proof['result'] and result['passed'] is True and result['target'] == target
            same_origin(result, F06_SOURCE, F06_RUN)
            manifest = json.loads(archive.read('manifest.json'))
            assert manifest['source_sha'] == F06_SOURCE and manifest['target'] == target
            assert manifest['sdk_version'] == manifest['producer']['sdk_version'] == '3.42.0'
            assert manifest['producer']['source_sha'] == F06_SOURCE
            assert str(manifest['provenance']['run_id']) == str(F06_RUN)
            assert str(manifest['provenance']['attempt']) == '1'
            assert manifest['archive'] == result['archive']
            payload = archive.read(result['archive']['name'])
            assert len(payload) == result['archive']['bytes']
            assert hashlib.sha256(payload).hexdigest() == result['archive']['sha256']
            with safe_zip(payload) as inner:
                assert hashlib.sha256(inner.read(entry_path)).hexdigest() == result['program_sha256']
            for member, field in [('configuration.json', 'configuration_sha256'),
                                  ('entry.json', 'entry_report_sha256')]:
                assert hashlib.sha256(archive.read(member)).hexdigest() == result[field]
            entry = json.loads(archive.read('entry.json'))
            if target == 'android':
                assert entry['launch_passed'] is True
                assert entry['installed_apk_sha256'] == result['program_sha256']
            elif target in ('iphone', 'ipad'):
                assert entry['launch_exit'] == 0
                assert entry['installed_executable_sha256'] == result['program_sha256']
            else:
                assert entry['passed'] is True
            if target == 'macos':
                launch = json.loads(archive.read('launch.json'))
                same_origin(launch, F06_SOURCE, F06_RUN)
                assert launch['passed'] is True and launch['executable_sha256'] == result['program_sha256']
            programs[target] = result['program_sha256']
    return {'scope_basis': 'six original archives, programs, entries and same-run summaries reauthenticated',
            'original_artifacts': F06_PINS, 'program_sha256': programs,
            'physical_device': False, 'full_behavioral_regression': False, 'formal_release': False}


def verify_macos_organization(spec, jobs):
    assert spec['adapter'] == 'macos_organization_40635727935'
    assert spec['run'] == MAC_ORG_RUN and spec['source_prefix'] == MAC_ORG_SOURCE
    assert spec['expected_conclusion'] == 'failure', 'original full run remains failed'
    matches = [job for job in jobs if job['id'] == 122642119295 and job['name'] == 'Organization macos']
    assert len(matches) == 1
    job = matches[0]
    assert job['head_sha'] == MAC_ORG_SOURCE and job['conclusion'] == 'success'
    for step_name in ('Exercise native organization and process restart',
                      'Verify native test results and retain evidence'):
        steps = [step for step in job['steps'] if step['name'] == step_name]
        assert len(steps) == 1 and steps[0]['conclusion'] == 'success'
    with evidence_zip(MAC_ORG_PIN, MAC_ORG_RUN, MAC_ORG_SOURCE,
                      'apple-organization-macos-40635727935-1') as archive:
        report = json.loads(archive.read('validated/organization-ui.json'))
        same_origin(report, MAC_ORG_SOURCE, MAC_ORG_RUN)
        assert report['platform'] == 'macos' and report['accepted'] is True and report['problems'] == []
        assert report['cases'] == list(MAC_ORG_CASES)
        assert report['executable_sha256'] == MAC_ORG_PROGRAM
        assert report['complete_product_accepted'] is False and report['physical_device_execution'] is False
        log = archive.read('xcodebuild.log').decode('utf-8')
        for case in MAC_ORG_CASES:
            assert re.search(r'\b' + re.escape(case) + r"\]' passed \(", log), case
        manifest = json.loads(archive.read('validated/attachments/manifest.json'))
        seen = set()
        def case_owner(name):
            found = re.findall(r'\btest[A-Za-z0-9_]+\b', name or '')
            assert len(found) == 1 and found[0] in MAC_ORG_CASES, 'unknown organization case'
            return found[0]
        for group in manifest:
            case = case_owner(group.get('testIdentifier') or group.get('testName'))
            for item in group['attachments']:
                title, filename = item['suggestedHumanReadableName'], item['exportedFileName']
                assert PurePosixPath(filename).name == filename and '\\' not in filename
                member = 'validated/attachments/' + filename
                info = archive.getinfo(member)
                assert 0 < info.file_size <= 16 * 1024 * 1024
                data = archive.read(member)
                if title.startswith('organization-steps-'):
                    role = 'steps'
                    payload = json.loads(data)
                    assert case_owner(payload['test']) == case and payload['steps'] == MAC_ORG_CASES[case]
                elif title.startswith('organization-screen-'):
                    role = 'screen'
                    assert data.startswith(b'\x89PNG\r\n\x1a\n')
                else:
                    continue
                assert (case, role) not in seen, 'duplicate case attachment'
                seen.add((case, role))
        assert seen == {(case, role) for case in MAC_ORG_CASES for role in ('steps', 'screen')}
    return {'artifact': MAC_ORG_PIN['id'], 'zip_sha256': MAC_ORG_PIN['sha256'],
            'passing_cases': list(MAC_ORG_CASES), 'authenticated_case_attachments': len(seen),
            'program_sha256_recorded_by_original_collector': MAC_ORG_PROGRAM,
            'completed_at': date(job['completed_at']).isoformat(),
            'original_run_conclusion': 'failure', 'accepted_platform': 'macos',
            'scope_basis': 'original Mac ZIP, exact six passing XCTest cases and original step/screenshot attachments; no iOS credit'}


def verify_evidence(pair):
    key, spec = pair
    try:
        doc_ref = spec.get('source_doc_commit', 'HEAD') + ':' + spec['doc']
        document = subprocess.check_output(['git', 'show', doc_ref])
        assert str(spec['run']).encode() in document, 'reference document does not name this run'
        run = fetch('actions/runs/' + str(spec['run']) + '/attempts/1')
        assert run['id'] == spec['run'] and run['run_attempt'] == 1
        assert run['status'] == 'completed', 'run not completed'
        assert run['conclusion'] == spec.get('expected_conclusion', 'success'), 'run conclusion differs'
        assert run['head_sha'].startswith(spec.get('source_prefix', '')), 'source identity differs'
        jobs = pages('actions/runs/' + str(spec['run']) + '/attempts/1/jobs', 'jobs')
        assert jobs and all(job['status'] == 'completed' for job in jobs)
        finished = max(date(job['completed_at']) for job in jobs if job.get('completed_at'))
        proof = {'run': spec['run'], 'attempt': 1, 'source': run['head_sha'],
                 'conclusion': run['conclusion'], 'completed_at': finished.isoformat(),
                 'scope_review_document': doc_ref, 'document_sha256': hashlib.sha256(document).hexdigest(),
                 'scope_basis': 'root-reviewed named scope in referenced source document'}
        if key == 'gtk_sync_account':
            # This one historical report records successful check names as
            # strings. Authenticate the exact original report and same-run
            # identity rather than interpreting arbitrary string lists.
            assert spec.get('adapter') == 'gtk_sync_account_40629444286'
            from gtk_sync_evidence import verify, RUN, SOURCE, ARCHIVE
            assert spec['run'] == RUN and spec['source_prefix'] == SOURCE
            assert spec['artifact'] == ARCHIVE[0] and spec['bytes'] == ARCHIVE[1] and spec['sha256'] == ARCHIVE[2]
            proof.update(verify())
        elif key == 'android_sync_account':
            assert spec.get('adapter') == 'android_sync_account_40630302205'
            from android_sync_evidence import verify, RUN, SOURCE, ARTIFACT, SIZE, SHA
            assert spec['run'] == RUN and spec['source_prefix'] == SOURCE
            assert spec['artifact'] == ARTIFACT and spec['bytes'] == SIZE and spec['sha256'] == SHA
            proof.update(verify())
        elif key == 'f06_sdk342_six_packages':
            proof.update(verify_f06(spec, jobs))
        elif key == 'macos_organization_original':
            proof.update(verify_macos_organization(spec, jobs))
        else:
            assert 'adapter' not in spec, 'unknown evidence adapter'
        if spec.get('required_cases'):
            item = fetch('actions/artifacts/' + str(spec['artifact']))
            assert not item['expired'] and item['workflow_run']['id'] == spec['run']
            assert item['workflow_run']['head_sha'] == run['head_sha']
            assert item['size_in_bytes'] == spec['bytes'], 'outer artifact byte count differs'
            assert item['digest'] == 'sha256:' + spec['sha256'], 'outer artifact API digest differs'
            raw = download_artifact_zip(spec['artifact'])
            assert len(raw) == spec['bytes'] and hashlib.sha256(raw).hexdigest() == spec['sha256']
            if spec.get('inner_zip'):
                inner = spec['inner_zip']
                with zipfile.ZipFile(io.BytesIO(raw)) as outer:
                    candidates = [outer.read(info) for info in outer.infolist()
                                  if info.filename.endswith('.zip') and info.file_size == inner['bytes']]
                candidates = [data for data in candidates if hashlib.sha256(data).hexdigest() == inner['sha256']]
                assert len(candidates) == 1, 'exact pinned inner ZIP absent or duplicated'
                proof['inner_zip'] = inner
            matching = []
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                names = archive.namelist()
                assert len(names) == len(set(names)), 'duplicate ZIP members'
                for member in names:
                    info = archive.getinfo(member)
                    if not member.endswith('.json') or info.file_size > 16 * 1024 * 1024:
                        continue
                    try:
                        value = json.loads(archive.read(member))
                    except (UnicodeError, ValueError):
                        continue
                    if not isinstance(value, dict):
                        continue
                    if spec.get('case_phase'):
                        if (value.get('source_sha') != run['head_sha'] or
                            str(value.get('run_id')) != str(spec['run']) or
                            str(value.get('attempt')) != '1' or
                            value.get('platform') != spec.get('platform') or
                            value.get('accepted') is not True):
                            continue
                        phases = [phase for phase in value.get('phases', [])
                                  if phase.get('mode') == spec['case_phase'] and phase.get('accepted') is True]
                        if len(phases) != 1:
                            continue
                        rows = phases[0].get('cases', [])
                        if not isinstance(rows, list) or len(rows) != spec['phase_case_count']:
                            continue
                        checks = {row.get('name'): row.get('result') == 'Passed'
                                  for row in rows if isinstance(row, dict)}
                    else:
                        rows = value.get('checks', [])
                        if not isinstance(rows, list):
                            continue
                        checks = {row.get('name'): row.get(spec.get('case_result_field', 'pass'))
                                  for row in rows if isinstance(row, dict)}
                    if all(checks.get(name) is True for name in spec['required_cases']):
                        matching.append(member)
            assert matching, 'required actual passing cases absent in authenticated original ZIP'
            proof.update(artifact=spec['artifact'], zip_sha256=spec['sha256'],
                         passing_cases=spec['required_cases'], report_members=matching,
                         scope_basis='named passing cases reread from authenticated original run ZIP')
        return key, {'ok': True, **proof}
    except Exception as error:
        return key, {'ok': False, 'run': spec['run'], 'error': repr(error)}


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'audit and artifact parsing are Actions-only'
    catalog_path = ROOT / 'docs/reader-total-progress/catalog.json'
    catalog_bytes = catalog_path.read_bytes()
    catalog = json.loads(catalog_bytes)
    rows = catalog['requirements']
    fixed = json.loads(subprocess.check_output(['git', 'show',
        '1adeabf2a672ddc0c200631e29897cfe76106afd:docs/reader-total-progress/catalog.json']))
    identity = lambda row: (row['id'], row['group'], row.get('platform'), row['title'])
    assert list(map(identity, rows)) == list(map(identity, fixed['requirements'])), 'fixed 108 item definitions changed'
    assert catalog['version'] == 'reader-v1-total-1' and len(rows) == 108
    assert len({row['id'] for row in rows}) == 108, 'duplicate requirement IDs'
    assert {group: sum(row['group'] == group for row in rows) for group in ('foundation', 'host', 'final')} == {
        'foundation': 12, 'host': 84, 'final': 12}
    assert all(sum(row.get('platform') == platform for row in rows) == 14
               for platform in ('windows', 'linux', 'macos', 'android', 'iphone', 'ipad'))
    assert all(row['state'] in ('verified', 'partial', 'pending') for row in rows)
    assert all(row['evidence'] for row in rows if row['state'] == 'verified')
    refs = catalog['evidence']
    assert all(ref in refs for row in rows for ref in row['evidence'])
    actual_scope_blob = subprocess.check_output(['git', 'rev-parse', 'HEAD:' + catalog['scope_document']], text=True).strip()
    assert actual_scope_blob == catalog['scope_document_blob'], 'original v1 scope changed'
    with ThreadPoolExecutor(max_workers=4) as pool:
        proofs = dict(pool.map(verify_evidence, refs.items()))
    cutoff = date(catalog['historical_cutoff_utc'])
    current, historical = [], []
    for row in rows:
        item = dict(row)
        item['counted'] = row['state'] == 'verified' and all(proofs[ref]['ok'] for ref in row['evidence'])
        item['completed_at'] = max((proofs[ref]['completed_at'] for ref in row['evidence']), default=None) if item['counted'] else None
        item['counted_at_historical_cutoff'] = bool(item['counted'] and date(item['completed_at']) <= cutoff)
        current.append(item)
        historical.append(item['counted_at_historical_cutoff'])
    problems = {key: value for key, value in proofs.items() if not value['ok']}
    current_count = sum(row['counted'] for row in current)
    historical_count = sum(historical)
    report = {'catalog_version': catalog['version'], 'catalog_sha256': hashlib.sha256(catalog_bytes).hexdigest(),
              'audit_source': os.environ['GITHUB_SHA'], 'audit_run': os.environ['GITHUB_RUN_ID'],
              'audit_attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'audited_at_utc': datetime.now(timezone.utc).isoformat(),
              'denominator': 108, 'scoring_definition': catalog['definition'], 'same_source_product_accepted': False,
              'historical_cutoff_utc': catalog['historical_cutoff_utc'],
              'historical_done': historical_count, 'historical_percent': round(100 * historical_count / 108, 1),
              'current_done': current_count, 'current_percent': round(100 * current_count / 108, 1),
              'percentage_point_change': round(100 * (current_count - historical_count) / 108, 1),
              'by_group': {group: {'done': sum(row['counted'] for row in current if row['group'] == group),
                                   'total': sum(row['group'] == group for row in current)}
                           for group in ('foundation', 'host', 'final')},
              'evidence_ok': not problems, 'problems': problems, 'evidence': proofs, 'requirements': current}
    out = ROOT / 'build/reader-total-progress'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    lines = ['# 完整首版固定验收目标审计', '', f'固定分母：108；catalog `{catalog["version"]}`。',
             f'昨日截止：{historical_count}/108（{report["historical_percent"]}%）。',
             f'当前：{current_count}/108（{report["current_percent"]}%）。',
             '', '这是固定功能验收工作覆盖率，不是剩余工时；最终同源码六平台产品尚未通过。', '',
             '| ID | 目标 | 当前计分 | 昨日计分 |', '|---|---|---|---|']
    lines += [f'| {row["id"]} | {row["title"]} | {int(row["counted"])} | {int(row["counted_at_historical_cutoff"])} |' for row in current]
    (out / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as summary:
        summary.write('\n'.join(lines[:7]) + '\n')
    print(json.dumps({key: report[key] for key in ('denominator','historical_done','historical_percent',
          'current_done','current_percent','percentage_point_change','by_group','evidence_ok','problems')}, ensure_ascii=False))
    if problems:
        raise SystemExit('Audit evidence incomplete; percentages are provisional until all problems are resolved')


if __name__ == '__main__':
    main()
