"""Actions-only authentication of the wave3 S18 joint-install artifacts.

Nothing here is produced by the runtime job: every job, artifact, ZIP byte, member
hash, program identity and business number is re-derived from this run and attempt.
Fifteen real byte-level mutations of the authenticated S16/S14/S17 evidence must be
refused by the same verifier before the result is written.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/reader-wave3-s18'
SEED = 'd263ce5228838ac90c0a0dc13a5193d4a7739681'
WORKFLOW = '.github/workflows/reader-wave3-s18.yml'
JOB = 'shared install ('
PLATFORMS = [('Linux', 'ubuntu-22.04'), ('Windows', 'windows-2022'), ('macOS', 'macos-15')]
PHASES = {'prepare', 'sdk341', 'sdk340', 'shared', 'families', 'graph', 'font', 'annotation',
          'jump', 'original', 'view'}
MAC_PEER = {'source_sha': '15dab6b2270dc296ed6239db67ced2e22d255e65', 'run_id': 40196978163,
            'artifact_id': 12600789926,
            'zip_sha256': '92be56ffa04d7c334d4811a42821a314089b4f8ae01746f0dfdf456b5eab9bd5'}


def need(condition, message, problems):
    if not condition:
        problems.append(message)


def verify_platform(archive, platform, source, run, attempt):
    problems = []
    result = json.loads(archive.read('result.json'))
    need((result['source_sha'], result['run_id'], result['attempt'], result['platform']) ==
         (source, run, attempt, platform), 'identity ' + platform, problems)
    need(result['seed'] == SEED, 'seed ' + platform, problems)
    need(result['runtime_accepted'] is True, 'runtime not accepted ' + platform, problems)
    need(result['legacy_guards_executed'] is False and result['complete_product'] is False, 'claims ' + platform, problems)
    need(result['adopted'] is False, 'adaptation claim ' + platform, problems)
    names = [name for name in archive.namelist() if not name.endswith('/')]
    need(len(names) == len(set(names)), 'duplicate member', problems)
    for name in names:
        need(not name.startswith('/') and '..' not in name.split('/') and '\\' not in name, 'unsafe member ' + name, problems)
    files = result['files']
    need(set(names) == set(files) | {'result.json'}, 'member set ' + platform,
         problems)
    for name, record in files.items():
        if name not in names:
            continue
        data = archive.read(name)
        need(len(data) == record['bytes'] and hashlib.sha256(data).hexdigest() == record['sha256'],
             'member hash ' + name, problems)
    need(len(result['programs']) >= 20, 'program count ' + platform, problems)
    for origin, record in result['programs'].items():
        need(files.get(record['member']) == {'bytes': record['bytes'], 'sha256': record['sha256']},
             'program binding ' + origin, problems)
        if record['member'] in names:
            data = archive.read(record['member'])
            need(len(data) == record['bytes'] and hashlib.sha256(data).hexdigest() == record['sha256'],
                 'program bytes ' + origin, problems)
    phases = result['phases']
    need(set(phases) == PHASES, 'phase set ' + platform, problems)
    for name in PHASES:
        need(phases.get(name, {}).get('passed') is True, 'phase failure ' + name, problems)
    if problems:
        return problems
    font = phases['font']
    need(font['checks'] == (61 if platform == 'Windows' else 60), 'S14 check count ' + platform, problems)
    need(font['preloaded_controls'] == 4, 'S14 preloaded controls', problems)
    need(font['negative_contracts'] == 42 and font['synthetic_platforms'] == 4, 'S14 negative contracts', problems)
    annotation = phases['annotation']
    need(annotation['mac_found_claimed'] is False, 'FOUND claimed for Mac records', problems)
    need(annotation['mac_heads'] >= 1 and annotation['mac_null_heads'] >= 1, 'Mac records', problems)
    need(annotation['legacy_all_equal'] is True, 'legacy equivalence', problems)
    jump = phases['jump']
    need(set(jump['original_checks']) == {'baseline', 'default', 'raw'}, 'original suites', problems)
    need(all(value >= 149 for value in jump['original_checks'].values()), 'original 149 ' + platform,
         problems)
    need(jump['raw_checks'] == 162 and jump['default_checks'] == 21, 'raw/default counts', problems)
    need(jump['programs'] == 9 and len(jump['archives']) == 3, 'nine programs three archives', problems)
    need(jump['default_equals_baseline'] is True, 'default equals baseline', problems)
    original = phases['original']
    need(original['checks'] == 44 and original['frozen_checks'] == 6, 'S15 checks', problems)
    need(original['target_controls'] == 16 and original['target_refusals'] == 8, 'S15 target controls', problems)
    view = phases['view']
    need(view['frozen_checks'] == 22 and view['raw_checks'] == 20, 'S17 checks', problems)
    need(len(view['mixed_refusals']) == 5, 'S17 mixed refusals', problems)
    reports = result['reports']
    for name in ('annotation.json', 's14-result.json', 's14-preloaded.json', 's14-negative-contracts.json',
                 's16-original-baseline.json', 's16-original-default.json', 's16-original-raw.json',
                 's16-raw.json', 's16-default.json', 's15-export.json', 's15-frozen.json', 's15-targets.json',
                 's17-frozen-legacy.json', 's17-raw.json', 'annotation-mac-peer.json'):
        need(name in reports, 'missing report ' + name, problems)
    if problems:
        return problems
    annotation_report = json.loads(archive.read(reports['annotation.json']['member']))
    need(annotation_report['accepted'] is True and annotation_report['failed'] == [], 'annotation accepted', problems)
    need(annotation_report['check_count'] == len(annotation_report['checks']), 'annotation check count', problems)
    peer = json.loads(archive.read(reports['annotation-mac-peer.json']['member']))
    need((peer['source_sha'], peer['run_id'], peer['artifact_id'], peer['zip_sha256']) ==
         (MAC_PEER['source_sha'], MAC_PEER['run_id'], MAC_PEER['artifact_id'], MAC_PEER['zip_sha256']),
         'the certified Mac artifact identity differs', problems)
    legacy = []
    for label in ('baseline', 'off', 'raw'):
        data = archive.read(reports['annotation-legacy-' + label + '-legacy.jsonl']['member'])
        legacy.append(hashlib.sha256(data).hexdigest())
        need(hashlib.sha256(data).hexdigest() == annotation_report['legacy_outputs']['jsonl'],
             'legacy jsonl identity ' + label, problems)
    need(len(set(legacy)) == 1, 'legacy annotation bytes differ inside one platform', problems)
    raw_summary = json.loads(archive.read(reports['s16-raw.json']['member']))
    need(raw_summary['accepted'] is True and raw_summary['checks_total'] == 162, 'S16 raw report', problems)
    default_summary = json.loads(archive.read(reports['s16-default.json']['member']))
    need(default_summary['accepted'] is True and default_summary['checks_total'] == 21, 'S16 default report', problems)
    for label in ('baseline', 'default', 'raw'):
        summary = json.loads(archive.read(reports['s16-original-' + label + '.json']['member']))
        need(summary['checks_total'] >= 149 and summary['checks_failed'] == 0, 'S16 original report ' + label, problems)
    exported = json.loads(archive.read(reports['s15-export.json']['member']))
    need(exported['accepted'] is True and len(exported['checks']) == 44, 'S15 export report', problems)
    frozen = json.loads(archive.read(reports['s17-frozen-legacy.json']['member']))
    need(frozen['accepted'] is True and frozen['count'] == 22, 'S17 frozen report', problems)
    explicit = json.loads(archive.read(reports['s17-raw.json']['member']))
    need(explicit['accepted'] is True and explicit['count'] == 20, 'S17 raw report', problems)
    preloaded = json.loads(archive.read(reports['s14-preloaded.json']['member']))
    need(preloaded['accepted'] is True and len(preloaded['cases']) == 4, 'S14 preloaded report', problems)
    contracts = json.loads(archive.read(reports['s14-negative-contracts.json']['member']))
    need(contracts['negative_cases'] == 42, 'S14 negative report', problems)
    return problems


def artifact_bytes(raw, replacement=None, removal=None, result_edit=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive, zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as output:
        for name in archive.namelist():
            if name == removal:
                continue
            data = archive.read(name)
            if name == replacement:
                data = data[:-1] + bytes([data[-1] ^ 0xff])
            if name == 'result.json' and result_edit is not None:
                value = json.loads(data)
                result_edit(value)
                data = json.dumps(value).encode('utf-8')
            output.writestr(name, data)
    return stream.getvalue()


def mutations(raw, platform, source, run, attempt):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        result = json.loads(archive.read('result.json'))
        programs = list(result['programs'])
        reports = result['reports']
    cases = []
    for name in programs[:9]:
        cases.append(('program:' + name, dict(replacement=result['programs'][name]['member'])))
    cases.append(('s16-raw-report', dict(replacement=reports['s16-raw.json']['member'])))
    cases.append(('s14-result', dict(replacement=reports['s14-result.json']['member'])))
    cases.append(('annotation-report', dict(replacement=reports['annotation.json']['member'])))
    cases.append(('attempt', dict(result_edit=lambda value: value.__setitem__('attempt', '9'))))

    def break_program(value):
        value['programs'][programs[0]]['sha256'] = '0' * 64
    cases.append(('program-identity', dict(result_edit=break_program)))
    cases.append(('missing-member', dict(removal=reports['s17-raw.json']['member'])))
    outcomes = []
    for name, edit in cases:
        payload = artifact_bytes(raw, **edit)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            problems = verify_platform(archive, platform, source, run, attempt)
        if not problems:
            raise AssertionError('the verifier accepted the mutation ' + name)
        outcomes.append({'name': name, 'rejected': True, 'problems': len(problems)})
    if len(outcomes) != 15:
        raise AssertionError(('mutation coverage', len(outcomes)))
    return outcomes


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    sys.path.insert(0, str(ROOT / 'tools'))
    from check_parallel_integration import fetch, pages, download_artifact_zip
    source, run, attempt = (os.environ[key] for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    metadata = fetch('actions/runs/' + run + '/attempts/' + attempt)
    assert metadata['head_sha'] == source and str(metadata['run_attempt']) == attempt
    assert metadata['path'].split('@')[0] == WORKFLOW, metadata['path']
    jobs = pages('actions/runs/' + run + '/attempts/' + attempt + '/jobs', 'jobs')
    artifacts = pages('actions/runs/' + run + '/artifacts', 'artifacts')
    summary = {'source_sha': source, 'run_id': run, 'attempt': attempt, 'runtime_accepted': False,
               'complete_product': False, 'platforms': [], 'mutation_controls': [], 'failures': []}
    checks = {}
    for platform, runner in PLATFORMS:
        job, = [row for row in jobs if row['name'] == JOB + runner + ')']
        assert job['head_sha'] == source and str(job['run_attempt']) == attempt
        assert job['status'] == 'completed' and job['conclusion'] == 'success'
        name = 'reader-wave3-s18-runtime-' + platform + '-' + run + '-' + attempt
        item, = [row for row in artifacts if row['name'] == name]
        assert item['expired'] is False and item['workflow_run']['head_sha'] == source
        assert str(item['workflow_run']['id']) == run
        assert datetime.fromisoformat(item['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc)
        raw = download_artifact_zip(item['id'])
        assert len(raw) == item['size_in_bytes']
        assert 'sha256:' + hashlib.sha256(raw).hexdigest() == item['digest']
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            problems = verify_platform(archive, platform, source, run, attempt)
            assert not problems, (platform, problems[:8])
            result = json.loads(archive.read('result.json'))
            frozen = json.loads(archive.read(result['reports']['s17-frozen-legacy.json']['member']))
            explicit = json.loads(archive.read(result['reports']['s17-raw.json']['member']))
            legacy = json.loads(archive.read(result['reports']['annotation.json']['member']))['legacy_outputs']
        checks[platform] = {'frozen': frozen['checks'], 'raw': explicit['checks'],
                            'legacy': [legacy['jsonl'], legacy['markdown']]}
        summary['mutation_controls'].append({'platform': platform,
                                             'controls': mutations(raw, platform, source, run, attempt)})
        summary['platforms'].append({
            'platform': platform, 'producer_job': job['id'], 'phase_count': len(result['phases']),
            'program_count': len(result['programs']), 'file_count': len(result['files']),
            's14_checks': result['phases']['font']['checks'],
            'annotation_checks': result['phases']['annotation']['checks'],
            'original_checks': result['phases']['jump']['original_checks'],
            'raw_checks': result['phases']['jump']['raw_checks'],
            'default_checks': result['phases']['jump']['default_checks'],
            's15_checks': result['phases']['original']['checks'],
            's15_target_controls': result['phases']['original']['target_controls'],
            's17_checks': [result['phases']['view']['frozen_checks'], result['phases']['view']['raw_checks']],
            'mixed_refusals': len(result['phases']['view']['mixed_refusals']),
            'artifact': {key: item[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')}})
    names = {platform: {'frozen': value['frozen'], 'raw': value['raw']} for platform, value in checks.items()}
    assert names['Linux'] == names['Windows'], 'the unchanged S17 contract requires Linux and Windows to agree'
    summary['linux_windows_checks_identical'] = True
    summary['macos_checks_identical'] = names['macOS'] == names['Linux']
    legacy = [tuple(value['legacy']) for value in checks.values()]
    assert len(set(legacy)) == 1, 'the legacy annotation bytes must be identical on every platform'
    summary['cross_platform_legacy_bytes_identical'] = True
    summary['runtime_accepted'] = True
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'runtime-strict.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=1), flush=True)


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / 'runtime-strict.json').write_text(
            json.dumps({'accepted': False, 'error': repr(error)}, indent=2) + '\n', encoding='utf-8')
        raise
