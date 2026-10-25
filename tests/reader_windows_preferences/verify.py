"""F3 strict same-source authentication; every retained strict gate stays intact."""
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
sys.path.insert(0, str(ROOT / 'tests/reader_windows_search'))
import verify as search
from check_parallel_integration import fetch, download_artifact_zip, require


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def bmp_inner(raw, pad=6):
    """Actual pixels away from the client edge of one 32-bit BMP capture."""
    width = int.from_bytes(raw[18:22], 'little')
    height = int.from_bytes(raw[22:26], 'little')
    require(raw[:2] == b'BM' and width > 2 * pad and height > 2 * pad, 'not a native BMP capture')
    stride = width * 4
    body = raw[54:]
    return b''.join(body[y * stride + pad * 4:(y + 1) * stride - pad * 4]
                    for y in range(pad, height - pad))


def validate(report, source, run, attempt, host, baseline):
    expected = search.names_from_source(Path(__file__).with_name('check_ui.py'), 'REQUIRED')
    search.bound(report, expected, source, run, attempt)
    require(report['consumer_sha256'] == host and report['baseline_sha256'] == baseline,
            'F3 used a different host or baseline')
    require(report['transport'] == 'SendInput+UIAutomation+Win32' and report['complete_product'] is False and
            report['performance_accepted'] is False and report['screen_reader_accepted'] is False,
            'invalid F3 scope')
    require(report['captures'] and all(name.endswith('.bmp') for name in report['captures']),
            'missing native captures')
    return len(expected)


def selftest():
    expected = search.names_from_source(Path(__file__).with_name('check_ui.py'), 'REQUIRED')
    source = os.environ['GITHUB_SHA']
    run, attempt = os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT']
    good = dict(accepted=True, source_sha=source, run_id=run, attempt=attempt, checks=expected,
                count=len(expected), problems=[], consumer_sha256='host', baseline_sha256='baseline',
                transport='SendInput+UIAutomation+Win32', complete_product=False,
                performance_accepted=False, screen_reader_accepted=False,
                captures=['default-on.bmp'])
    validate(good, source, run, attempt, 'host', 'baseline')
    mutations = [dict(accepted=False), dict(source_sha='0' * 40), dict(run_id='0'), dict(attempt='0'),
                 dict(count=0), dict(checks=[]), dict(checks=expected[:-1]),
                 dict(checks=expected + ['extra']), dict(problems=['injected']),
                 dict(consumer_sha256='other'), dict(baseline_sha256='other'),
                 dict(transport='report only'), dict(complete_product=True),
                 dict(performance_accepted=True), dict(screen_reader_accepted=True),
                 dict(captures=[]), dict(captures=['report.json'])]
    rejected = 0
    for mutation in mutations:
        bad = copy.deepcopy(good)
        bad.update(mutation)
        try:
            validate(bad, source, run, attempt, 'host', 'baseline')
        except (ValueError, KeyError):
            rejected += 1
        else:
            raise ValueError('F3 strict verifier accepted a malformed report')
    return rejected


def main(workflow_path='.github/workflows/reader-windows-preferences-ui.yml'):
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    if sys.argv[1:] == ['--protocol-selftest']:
        print(json.dumps({'preferences_protocol_rejections': selftest()}))
        return
    retained = module('retained_records', ROOT / 'tests/reader_windows_records/verify.py')
    retained.main(workflow_path)
    source = os.environ['GITHUB_SHA']
    run = int(os.environ['GITHUB_RUN_ID'])
    attempt = int(os.environ['GITHUB_RUN_ATTEMPT'])
    out = Path('build/wprefs-summary')
    out.mkdir(parents=True, exist_ok=False)
    result = dict(accepted=False, source_sha=source, run_id=run, attempt=attempt, problems=[],
                  complete_product=False, performance_accepted=False, screen_reader_accepted=False)
    try:
        require(os.environ['SEARCH_RESULT'] == 'success', 'native Windows job did not pass')
        info = fetch('actions/runs/%d' % run)
        require(info['head_sha'] == source and info['run_attempt'] == attempt and
                info['path'].split('@')[0] == workflow_path, 'wrong workflow identity')
        jobs = fetch('actions/runs/%d/attempts/%d/jobs?per_page=100' % (run, attempt))['jobs']
        matching = [job for job in jobs if job['name'] == 'installed F1 and native Windows search controls and lifecycle']
        require(len(matching) == 1 and matching[0]['head_sha'] == source and
                matching[0]['conclusion'] == 'success', 'wrong native Windows job')
        steps = {step['name']: step['conclusion'] for step in matching[0]['steps']}
        require(steps.get('Execute real native F3 settings, page theme and persistence') == 'success',
                'the F3 native step did not pass')
        identity = int(os.environ['ARTIFACT_ID'])
        meta = fetch('actions/artifacts/%d' % identity)
        require(meta['name'] == 'reader-windows-search-initial-%d-%d' % (run, attempt) and
                meta['workflow_run']['id'] == run and meta['workflow_run']['head_sha'] == source and
                meta['expired'] is False and meta['size_in_bytes'] > 0 and
                datetime.fromisoformat(meta['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc),
                'bad artifact identity/expiry')
        with tempfile.TemporaryFile() as stream:
            download_artifact_zip(identity, stream)
            stream.seek(0)
            raw = stream.read()
        digest = hashlib.sha256(raw).hexdigest()
        require(len(raw) == meta['size_in_bytes'] and meta.get('digest') == 'sha256:' + digest and
                os.environ['UPLOAD_DIGEST'].removeprefix('sha256:') == digest, 'ZIP size or digest mismatch')
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            require(len(z.namelist()) == len(set(z.namelist())), 'duplicate ZIP member/report')

            def sha(path):
                return hashlib.sha256(z.read(path)).hexdigest()

            def load(path):
                return json.loads(z.read(path))

            host = sha('wprefs-package/EXReader/EXReader.exe')
            baseline = sha('ws-package/EXReader/EXReader.exe')
            report = load('wprefs-ui/preferences-ui.json')
            count = validate(report, source, run, attempt, host, baseline)
            for name in report['captures']:
                require(z.read('wprefs-ui/captures/' + name).startswith(b'BM'), 'missing native capture ' + name)
            # Independent re-assertions of the two pixel claims: the untouched
            # installation and a fixed page are byte-identical; the reflow page
            # theme really changed the canvas.
            require(bmp_inner(z.read('wprefs-ui/captures/default-on.bmp')) ==
                    bmp_inner(z.read('wprefs-ui/captures/default-off.bmp')),
                    'default rendering differs from the option-off host')
            require(bmp_inner(z.read('wprefs-ui/captures/fixed-light.bmp')) ==
                    bmp_inner(z.read('wprefs-ui/captures/fixed-dark.bmp')),
                    'fixed page content changed with the theme')
            require(bmp_inner(z.read('wprefs-ui/captures/picture-light.bmp')) !=
                    bmp_inner(z.read('wprefs-ui/captures/picture-dark.bmp')),
                    'the reflow page theme did not change the canvas')
            document = load('wprefs-ui/profile/preferences.json')
            require(len(document) == 14 and document['format'] == 'exreader-preferences' and
                    document['format_version'] == 1, 'missing public F3 document')
            mapping = z.read('wprefs-host/windows-host.map').decode('utf-8', errors='replace')
            for symbol in ('exr_render_page_background', 'reader_preferences_save', 'reader_preferences_load'):
                require(symbol in mapping, 'installed F3 or page-background symbol missing: ' + symbol)
            cloud = load('wio-cloud-module/result.json')
            require(cloud['accepted'] is True and cloud['count'] == 47 and len(cloud['checks']) == 47,
                    'original J01 named scenarios changed')
            bulk = load('wio-bulk-module/report.json')
            bulk_contract = module('bulk_contract', ROOT / 'tests/reader_bulk_organization/check_artifacts.py')
            bulk_contract.require_report(bulk, source, 21, str(run), str(attempt))
            f2 = load('ws-navigation-module-evidence/probe.json')
            require(len(f2['checks']) == 130, 'original F2 count changed')
        result.update(accepted=True, preferences_ui_checks=count, original_j01_checks=47,
                      original_f2_checks=130, original_strict_verifiers_preserved=True,
                      consumer_sha256=host, baseline_sha256=baseline,
                      job_id=matching[0]['id'],
                      artifact={key: meta[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
    except Exception as error:
        result['problems'].append(type(error).__name__ + ': ' + str(error))
    (out / 'verified.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result), flush=True)
    require(result['accepted'], 'F3 strict acceptance rejected')


if __name__ == '__main__':
    main()
