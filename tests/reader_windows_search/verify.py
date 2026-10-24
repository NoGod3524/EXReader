"""Actions-only same-run ZIP authentication for the real native search host."""
import ast
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip, require

RETAINED = {
    'account-product10/product-result.json': 10,
    'account-worker5/worker-result.json': 5,
    'account-shelf-ui/shelf-result.json': 13,
    'account-metadata-ui/metadata-ui.json': 18,
    'account-ui/account-ui.json': 32,
    'account-a11y/a11y-ui.json': 24,
}


def names_from_source(file, variable):
    for node in ast.parse(file.read_text(encoding='utf-8')).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == variable for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('missing named check contract: ' + variable)


def bound(report, expected, source, run, attempt):
    require(report.get('accepted') is True and report.get('source_sha') == source and
            str(report.get('run_id')) == str(run) and str(report.get('attempt')) == str(attempt),
            'report source/run/attempt/acceptance mismatch')
    checks = report.get('checks')
    require(isinstance(checks, list) and all(isinstance(x, str) for x in checks) and
            len(checks) == len(set(checks)) and report.get('count') == len(checks), 'bad named checks')
    require((set(checks) == set(expected) and len(checks) == len(expected)) if isinstance(expected, list)
            else len(checks) == expected, 'missing or extra named checks')
    require(not report.get('problems') and not report.get('failures'), 'reported host failure')
    return len(checks)


def protocol_selftest(source, run, attempt):
    good = {'accepted': True, 'source_sha': source, 'run_id': str(run), 'attempt': str(attempt),
            'checks': ['one', 'two'], 'count': 2, 'problems': []}
    mutations = [dict(accepted=False), dict(source_sha='0' * 40), dict(run_id='0'), dict(attempt='0'),
                 dict(checks=['one'], count=1), dict(checks=['one', 'one']), dict(count=3),
                 dict(problems=['injected failure']), dict(checks=['one', 'two', 'extra'], count=3)]
    for mutation in mutations:
        bad = copy.deepcopy(good);bad.update(mutation)
        try:
            bound(bad, ['one', 'two'], source, run, attempt)
        except ValueError:
            continue
        raise ValueError('validator accepted mutation: ' + repr(mutation))
    bound(good, ['one', 'two'], source, run, attempt)
    return len(mutations)


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    source = os.environ['GITHUB_SHA'];run = int(os.environ['GITHUB_RUN_ID']);attempt = int(os.environ['GITHUB_RUN_ATTEMPT'])
    out = Path('build/winsearch-summary');out.mkdir(parents=True, exist_ok=False)
    result = dict(accepted=False, source_sha=source, run_id=run, attempt=attempt, problems=[],
                  complete_product=False, performance_accepted=False, screen_reader_accepted=False)
    try:
        require(os.environ['SEARCH_RESULT'] == 'success', 'native Windows job did not pass')
        info = fetch('actions/runs/%d' % run)
        require(info['head_sha'] == source and info['run_attempt'] == attempt and
                info['path'].split('@')[0] == '.github/workflows/reader-windows-search-ui.yml', 'wrong workflow identity')
        jobs = fetch('actions/runs/%d/attempts/%d/jobs?per_page=100' % (run, attempt))['jobs']
        matches = [j for j in jobs if j['name'] == 'installed F1 and native Windows search controls and lifecycle']
        require(len(matches) == 1 and matches[0]['head_sha'] == source and matches[0]['conclusion'] == 'success', 'wrong native job')
        steps = {s['name']: s['conclusion'] for s in matches[0]['steps']}
        for name in ('Execute installed original F1 C and C++ consumers',
                     'Package and execute initial real Win32 TXT controls',
                     'Execute EPUB, PDF, provider refusal and live cancellation on the shared native host',
                     'Execute real keyboard and UI Automation search controls',
                     'Run every retained Windows account host regression'):
            require(steps.get(name) == 'success', 'required real step did not succeed: ' + name)
        identity = int(os.environ['ARTIFACT_ID']);meta = fetch('actions/artifacts/%d' % identity)
        require(meta['name'] == 'reader-windows-search-initial-%d-%d' % (run, attempt) and
                meta['workflow_run']['id'] == run and meta['workflow_run']['head_sha'] == source and
                meta['expired'] is False and meta['size_in_bytes'] > 0 and
                datetime.fromisoformat(meta['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc), 'bad artifact identity/expiry')
        with tempfile.TemporaryFile() as stream:
            download_artifact_zip(identity, stream);stream.seek(0);raw = stream.read()
        digest = hashlib.sha256(raw).hexdigest()
        require(len(raw) == meta['size_in_bytes'] and meta.get('digest') == 'sha256:' + digest and
                os.environ['UPLOAD_DIGEST'].removeprefix('sha256:') == digest, 'ZIP size or digest mismatch')
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            require(len(z.namelist()) == len(set(z.namelist())), 'duplicate ZIP entries')
            def load(path):
                return json.loads(z.read(path).decode('utf-8'))
            def sha(path):
                return hashlib.sha256(z.read(path)).hexdigest()
            product = sha('ws-package/EXReader/EXReader.exe')
            review = sha('ws-host/EXReaderShelfReview.exe')
            require(product == sha('ws-host/EXReaderProduct.exe') and product != review, 'candidate/review binary mismatch')
            root = Path(__file__).resolve().parent
            contracts = {
                'ws-search-ui/search-ui.json': names_from_source(root / 'check_ui.py', 'REQUIRED'),
                'ws-search-formats/formats-and-lifecycle.json': names_from_source(root / 'check_formats.py', 'REQUIRED') + names_from_source(root / 'check_formats.py', 'LIFECYCLE'),
                'ws-search-keyboard/keyboard-uia.json': names_from_source(root / 'check_keyboard.py', 'REQUIRED'),
            }
            counts = {}
            for path, names in contracts.items():
                report = load(path);counts[path] = bound(report, names, source, run, attempt)
                require(report['consumer_sha256'] == product, 'report used another candidate: ' + path)
                if 'review_sha256' in report:
                    require(report['review_sha256'] == review, 'report used another isolated worker')
            for path, count in RETAINED.items():
                counts[path] = bound(load(path), count, source, run, attempt)
            keyboard = load('ws-search-keyboard/keyboard-uia.json')
            require(keyboard['transport'] == 'SendInput+UIAutomation' and keyboard['screen_reader_accepted'] is False, 'wrong keyboard evidence')
            original = load('account-ui158/summary.json')
            require(original['passed'] is True and original['counts'] == {'steps': 158, 'passed': 158, 'failed': 0} and not original['errors'], 'original158 failed')
            evidence = load('account-ui158/wp13-windows-evidence.json')
            require(evidence['source_sha'] == source and evidence['identities_unchanged'] is True, 'original158 source mismatch')
            negative = load('account-negative/checks.json')
            require(negative['passed'] is True and len(negative['checks']) >= 26, 'original rejection cases incomplete')
            module = load('ws-search-module-evidence/result.json')
            require(module['accepted'] is True and module['source_sha'] == source and str(module['run_id']) == str(run) and
                    str(module['attempt']) == str(attempt) and module['checks'] == 264 and
                    module['probe_sha256'] == sha('ws-search-consumer/search-probe.exe') and
                    module['c_consumer_sha256'] == sha('ws-search-consumer/search-c-consumer.exe'), 'original F1 evidence mismatch')
            checks = load('ws-search-module-evidence/probe.json')['checks']
            # The unchanged F1 probe deliberately repeats its argument-contract
            # assertion for different inputs; retain its original case contract.
            required_f1 = names_from_source(root.parent / 'reader_search' / 'check_search.py', 'REQUIRED_CHECKS')
            cases = module['cases']
            required_cases = names_from_source(root.parent / 'reader_search' / 'check_search.py', 'REQUIRED_CASES')
            require(len(checks) == 264 and all(c['pass'] is True for c in checks) and
                    set(required_f1) <= {c['name'] for c in checks} and
                    len(cases) == len({c['id'] for c in cases}) and
                    set(required_cases) <= {c['id'] for c in cases}, 'F1 checks/cases incomplete')
        result.update(accepted=True, counts=counts, original_ui158=158, original_f1_checks=264,
                      protocol_rejections=protocol_selftest(source, run, attempt),
                      job=matches[0]['id'], artifact={k: meta[k] for k in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')},
                      consumer_sha256=product, review_sha256=review)
    except Exception as e:
        result['problems'].append(type(e).__name__ + ': ' + str(e))
    (out / 'verified.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True), flush=True)
    require(result['accepted'], 'native search same-run strict summary rejected')


if __name__ == '__main__':
    main()
