"""Original Windows judges with one explicit independent baseline-root adapter."""
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import download_artifact_zip, fetch, require
from identity import FILES, FLAGS

WORKFLOW = '.github/workflows/reader-windows-341-common.yml'
JOB = 'installed F1 and native Windows search controls and lifecycle'
OLD_ROOT = "baseline = sha('ws-package/EXReader/EXReader.exe')"
NEW_ROOT = "baseline = sha('baseline-package/EXReader/EXReader.exe')"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def original_f3():
    path = ROOT / 'tests/reader_windows_preferences/verify.py'
    code = path.read_text()
    require(code.count(OLD_ROOT) == 1, 'original F3 baseline adapter is no longer one literal path')
    # Retain every original F3 assertion and the complete recursive F1/F2/records
    # judges. Only the explicit 3.40 baseline ZIP root differs from old W01.
    value = type(sys)('common_f3_original')
    value.__file__ = str(path)
    exec(compile(code.replace(OLD_ROOT, NEW_ROOT), str(path), 'exec'), value.__dict__)
    return value


def validate_identity(value, source, run, attempt):
    require(value.get('source_sha') == source and str(value.get('run_id')) == str(run) and str(value.get('attempt')) == str(attempt), 'identity source/run/attempt')
    require(value.get('sdk_version') == '3.41.0' and value.get('sdk_abi') == 1 and
            value.get('sdk_source') == 'edddc463c06ed5731195cdb8f06b2df6dff7699e' and
            value.get('baseline_sdk_version') == '3.40.0' and
            value.get('baseline_source') == '9854061be331fe603a1822d9b2b36ee357154927', 'actual SDK/baseline scope')
    require(value.get('full_host_options') == {flag: True for flag in FLAGS} and set(value.get('files', {})) == set(FILES), 'complete enabled host/file set')
    files = value['files']
    require(files['production']['sha256'] == files['packaged_production']['sha256'] == files['f3_production']['sha256'], 'F3 and retained suites did not use one production')
    require(len({files[name]['sha256'] for name in ('production', 'shelf_review', 'atomic_review', 'old_veto_control', 'baseline')}) == 5, 'real production/reviews/control/baseline not distinct')
    require(value.get('complete_product') is False, 'broader product scope')


def selftest():
    original_f3()  # Parse the exact one-path adapter in Actions, never locally.
    good = dict(source_sha='source', run_id=1, attempt=2, sdk_version='3.41.0', sdk_abi=1,
        sdk_source='edddc463c06ed5731195cdb8f06b2df6dff7699e', baseline_sdk_version='3.40.0',
        baseline_source='9854061be331fe603a1822d9b2b36ee357154927', full_host_options={flag: True for flag in FLAGS},
        files={name: dict(sha256=name) for name in FILES}, complete_product=False)
    for name in ('packaged_production', 'f3_production'): good['files'][name]['sha256'] = 'production'
    validate_identity(good, 'source', 1, 2)
    mutations = [dict(source_sha='foreign'), dict(run_id=3), dict(attempt=1), dict(sdk_version='3.40.0'),
        dict(sdk_abi=2), dict(sdk_source='foreign'), dict(baseline_sdk_version='3.41.0'),
        dict(baseline_source='foreign'), dict(full_host_options={}), dict(files={}), dict(complete_product=True)]
    rejected = 0
    for change in mutations:
        bad = copy.deepcopy(good); bad.update(change)
        try: validate_identity(bad, 'source', 1, 2)
        except (ValueError, KeyError): rejected += 1; continue
        raise ValueError('common Windows protocol admitted '+repr(change))
    for name, digest in [('f3_production', 'other'), ('old_veto_control', 'atomic_review')]:
        bad = copy.deepcopy(good); bad['files'][name]['sha256'] = digest
        try: validate_identity(bad, 'source', 1, 2)
        except (ValueError, KeyError): rejected += 1; continue
        raise ValueError('common Windows binary substitution admitted')
    require(rejected == 13, 'common Windows protocol control omitted')
    return rejected


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    controls = selftest()
    if '--self-test' in sys.argv:
        print('13 common Windows identity refusals passed'); return
    f3 = original_f3()
    atomic = module('original_atomic_commit', ROOT / 'tests/reader_windows_preferences/verify_commit.py')
    atomic.selftest()
    source, run, attempt = os.environ['GITHUB_SHA'], int(os.environ['GITHUB_RUN_ID']), int(os.environ['GITHUB_RUN_ATTEMPT'])
    out = ROOT / 'build/windows-341-summary'; out.mkdir(parents=True, exist_ok=False)
    common = dict(accepted=False, source_sha=source, run_id=run, attempt=attempt, problems=[],
        sdk_version='3.41.0', sdk_abi=1, complete_product=False, performance_accepted=False,
        physical_device_execution=False, upgrade_accepted=False, bidirectional_accepted=False)
    full = dict(common, scope='Windows SDK3.41 same full native host: original retained suites plus F3 25')
    boundary = dict(common, scope='Windows SDK3.41 actual full-host atomic preference commit13 and old-veto control')
    try:
        f3.main(WORKFLOW)  # All original strict judges, assertions and negatives.
        # Run the entire original import/organization strict chain in its own
        # report directory; it retains all public readback/hash/negative checks.
        import_judge = module('original_import_organize', ROOT / 'tests/reader_windows_import_organize/verify.py')
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                import_judge.main(WORKFLOW)
                import_full = json.loads(Path('build/wio-summary/verified.json').read_text())
            finally:
                os.chdir(previous)
        meta = fetch('actions/artifacts/' + os.environ['ARTIFACT_ID'])
        require(meta['name'] == 'reader-windows-search-initial-%d-%d' % (run, attempt) and
                meta['workflow_run']['head_sha'] == source and meta['workflow_run']['id'] == run and
                meta['expired'] is False and datetime.fromisoformat(meta['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc), 'raw artifact identity/expiry')
        with tempfile.TemporaryFile() as stream:
            download_artifact_zip(meta['id'], stream); stream.seek(0); raw = stream.read()
        require(len(raw) == meta['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == meta['digest'], 'actual raw ZIP bytes/digest')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            require(len(archive.namelist()) == len(set(archive.namelist())), 'duplicate ZIP member')
            load = lambda path: json.loads(archive.read(path))
            value = load('windows-341-identity.json'); validate_identity(value, source, run, attempt)
            catalog = module('common_catalog_adapter', ROOT / 'tests/reader_windows_341/catalog.py')
            catalog_proof = load('windows-341-catalog-adapter.json')
            catalog_source = catalog.PATH.read_text()
            require(catalog_source.count(catalog.OLD) == 1 and
                    catalog_proof['source_sha'] == source and str(catalog_proof['run_id']) == str(run) and
                    str(catalog_proof['attempt']) == str(attempt) and catalog_proof['changed_literal_count'] == 1 and
                    catalog_proof['expected_runtime'] == '3.41.0' and catalog_proof['original_assertions_retained'] is True and
                    catalog_proof['original_source_sha256'] == hashlib.sha256(catalog_source.encode()).hexdigest() and
                    catalog_proof['adapted_source_sha256'] == hashlib.sha256(catalog_source.replace(catalog.OLD, catalog.NEW).encode()).hexdigest(),
                    'original catalog identity adaptation differs')
            for name, record in value['files'].items():
                require(record['path'] == FILES[name], 'substituted actual file path')
                content = archive.read(record['path'])
                require(len(content) == record['bytes'] and hashlib.sha256(content).hexdigest() == record['sha256'], 'actual SDK/program/map/cache bytes differ: '+name)
            production = value['files']['production']['sha256']
            review = value['files']['atomic_review']['sha256']; control = value['files']['old_veto_control']['sha256']
            for key in ('production_map', 'atomic_map', 'control_map'):
                text = archive.read(FILES[key]).decode('utf-8', errors='replace')
                for symbol in ('exr_render_page_background', 'reader_preferences_save', 'reader_preferences_load',
                               'reader_search_next', 'reader_navigation_resolve_cfi', 'reader_rc_apply', 'reader_av_page_get',
                               'reader_cloud_import', 'reader_bulk_'):
                    require(symbol in text, 'same full SDK3.41 host map missing '+symbol+' in '+key)
            cache = archive.read(FILES['host_cache']).decode('utf-8')
            require('EXR_SDK_VERSION:STRING=3.41.0' in cache and all('EXR_READER_WINDOWS_'+flag+':BOOL=ON' in cache for flag in FLAGS), 'host cache option/source drift')
            require('#define EXR_VERSION "3.41.0"' in archive.read(FILES['sdk_header']).decode('utf-8') and
                    'set(PACKAGE_VERSION "3.41.0")' in archive.read(FILES['sdk_version']).decode('utf-8') and
                    '#define EXR_VERSION "3.40.0"' in archive.read(FILES['baseline_header']).decode('utf-8'), 'actual SDK install identities differ')
            report = load('wprefs-commit-ui/report.json')
            atomic.validate(report, source, run, attempt, review, control)
            f3_report = load('wprefs-ui/preferences-ui.json')
            require(f3.validate(f3_report, source, run, attempt, production, value['files']['baseline']['sha256']) == 25, 'original full F3 count changed')
            require(import_full['accepted'] is True and import_full['consumer_sha256'] == production,
                    'original full import strict chain used another production')
            import_count = import_full['ui_checks']
        jobs = fetch('actions/runs/%d/attempts/%d/jobs?per_page=100' % (run, attempt))['jobs']
        producer, = [row for row in jobs if row['name'] == JOB]
        require(producer['head_sha'] == source and producer['run_attempt'] == attempt and producer['conclusion'] == 'success' and
                all(step['conclusion'] in ('success', 'skipped') for step in producer['steps']), 'full producer incomplete/hidden failure')
        artifact = {key: meta[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')}
        facts = dict(artifact=artifact, producer_job=producer['id'], identity=value, protocol_rejections=controls,
            catalog_identity_adapter=catalog_proof,
            consumer_sha256=production, atomic_review_sha256=review, old_veto_control_sha256=control,
            production_map_sha256=value['files']['production_map']['sha256'], original_judges_preserved=True)
        full.update(facts, accepted=True, f3_checks=25, original_f1_checks=264, original_f2_checks=130,
            navigation_checks=31, records_checks=32, original_ui158=158, original_j01_checks=47,
            original_j10_checks=21, import_organize_checks=import_count,
            import_organize_summary=import_full,
            retained_summaries={name: json.loads((ROOT / 'build' / name / 'verified.json').read_text())
                                for name in ('winsearch-summary', 'winnav-summary', 'winrecords-summary', 'wprefs-summary')})
        boundary.update(facts, accepted=True, checks=13, atomic_report=report, original_atomic_protocol_rejections=9,
            original_f3_suite_accepted=False)
    except Exception as error:
        full['problems'].append(type(error).__name__+': '+str(error)); boundary['problems'] = list(full['problems'])
    (out / 'full-f3.json').write_text(json.dumps(full, indent=2)+'\n')
    (out / 'atomic13.json').write_text(json.dumps(boundary, indent=2)+'\n')
    print(json.dumps(dict(full_f3_accepted=full['accepted'], atomic13_accepted=boundary['accepted'], problems=full['problems'])), flush=True)
    require(full['accepted'] and boundary['accepted'], 'complete SDK3.41 Windows scope refused')


if __name__ == '__main__':
    main()
