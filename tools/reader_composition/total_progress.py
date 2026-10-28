# SPDX-License-Identifier: MIT
"""Audit a fixed reader-v1 requirement catalog in Actions; never grant product acceptance."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, pages, download_artifact_zip


def date(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


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
