"""Reuse repository API/ZIP transport; strictly authenticate only this Actions attempt."""
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_parallel_integration import fetch, pages, download_artifact_zip
from check_docs import REQUIRED

SOURCE, RUN, ATTEMPT = (os.environ.get(k) for k in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))

def validate(report):
    assert report['source_sha'] == SOURCE and str(report['run_id']) == RUN and str(report['attempt']) == ATTEMPT
    assert report['accepted'] is True and report['guide_reviewed'] is True and report['links_accepted'] is True
    assert report['product_accepted'] is False and report['complete_product'] is False
    names = [x['name'] for x in report['checks']]
    assert len(names) == len(set(names)) and set(names) == REQUIRED
    assert all(x['ok'] is True for x in report['checks']) and not report['errors']
    assert report['steps_total'] == 17 and report['source_checked'] > 40
    assert report['files'] and report['external'] and all(x['ok'] for x in report['external'])

def zip_check(raw, metadata):
    assert len(raw) == metadata['size_in_bytes'] > 0
    assert 'sha256:' + hashlib.sha256(raw).hexdigest() == metadata['digest']
    assert metadata['expired'] is False
    assert datetime.fromisoformat(metadata['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc)
    assert metadata['workflow_run']['head_sha'] == SOURCE and str(metadata['workflow_run']['id']) == RUN

def get_artifact(role):
    name = 'reader-final-d07-' + role + '-' + RUN + '-' + ATTEMPT
    matches = [x for x in pages('actions/runs/' + RUN + '/artifacts', 'artifacts') if x['name'] == name]
    assert len(matches) == 1, 'missing or duplicate artifact: ' + name
    metadata = matches[0]
    raw = download_artifact_zip(metadata['id'])
    zip_check(raw, metadata)
    return raw, metadata

def entry(metadata):
    return {k: metadata[k] for k in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')}

def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    run = fetch('actions/runs/' + RUN)
    assert run['head_sha'] == SOURCE and str(run['run_attempt']) == ATTEMPT
    assert run['path'] == '.github/workflows/reader-final-d07.yml'
    if '--self-zip' in sys.argv:
        raw, metadata = get_artifact('evidence')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            assert archive.namelist() == ['verified.json']
            report = json.loads(archive.read('verified.json'))
            assert report['source_sha'] == SOURCE and report['run_id'] == RUN and report['attempt'] == ATTEMPT
            assert report['accepted'] is True
        print('D07_SELF_ZIP_AUTHENTICATED=' + json.dumps(entry(metadata)), flush=True)
        return
    output = Path('build/reader-final-d07/evidence')
    output.mkdir(parents=True, exist_ok=True)
    summary = {'source_sha': SOURCE, 'run_id': RUN, 'attempt': ATTEMPT, 'accepted': False,
               'product_accepted': False, 'complete_product': False, 'problems': []}
    try:
        jobs = pages('actions/runs/' + RUN + '/attempts/' + ATTEMPT + '/jobs', 'jobs')
        producer = [x for x in jobs if x['name'] == 'D07 document audit']
        assert len(producer) == 1
        job = producer[0]
        assert job['head_sha'] == SOURCE and job['status'] == 'completed' and job['conclusion'] == 'success'
        assert str(job['run_attempt']) == ATTEMPT
        raw, metadata = get_artifact('payload')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            assert len(names) == len(set(names)), 'duplicate ZIP members'
            assert 'report.json' in names
            report = json.loads(archive.read('report.json'))
            validate(report)
            expected = {'report.json'} | {'inputs/' + p for p in report['files']}
            assert set(names) == expected, 'payload missing=%r extra=%r' % (sorted(expected - set(names)), sorted(set(names) - expected))
            for path, digest in report['files'].items():
                data = archive.read('inputs/' + path)
                assert hashlib.sha256(data).hexdigest() == digest
                assert data == Path(path).read_bytes(), 'not current source bytes: ' + path
        # Exercise actual acceptance boundaries, not expected-rejection product tests.
        negatives = []
        for label in ('wrong_source', 'missing_case', 'duplicate_case', 'false_grant'):
            bad = copy.deepcopy(report)
            if label == 'wrong_source': bad['source_sha'] = '0' * 40
            elif label == 'missing_case': bad['checks'].pop()
            elif label == 'duplicate_case': bad['checks'].append(bad['checks'][0])
            else: bad['product_accepted'] = True
            try: validate(bad)
            except AssertionError: negatives.append(label)
            else: raise AssertionError('accepted ' + label)
        try: zip_check(raw + b'tamper', metadata)
        except AssertionError: negatives.append('tampered_zip')
        else: raise AssertionError('accepted tampered ZIP')
        summary.update(accepted=True, guide_reviewed=True, links_accepted=True,
                       artifact=entry(metadata), producer_job={'id': job['id'], 'name': job['name'], 'conclusion': job['conclusion']},
                       negatives_rejected=negatives, steps_total=report['steps_total'], source_checked=report['source_checked'],
                       links_total=report['links_total'], external=report['external'], checks=report['checks'],
                       program=report['program'], target=report['target'], sdk_identity=report['sdk_identity'],
                       files=report['files'], scope=report['review_scope'])
    except Exception as error:
        summary['problems'].append(str(error))
    (output / 'verified.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print('D07_VERIFIED=' + json.dumps(summary, ensure_ascii=False), flush=True)
    assert summary['accepted'], summary['problems']

if __name__ == '__main__':
    main()
