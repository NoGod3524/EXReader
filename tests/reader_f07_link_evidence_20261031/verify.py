"""Actions-only full retained link-log diagnosis. Never execute artifact code."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
LOCK = json.loads((HERE / 'source_lock.json').read_text())
OUT = ROOT / 'build/f07-link-evidence'
OLD = 'tests/reader_f07_desktop_provider_20261031/verify.py'
SCOPE = {
    'tests/reader_f07_link_evidence_20261031/verify.py',
    'tests/reader_f07_link_evidence_20261031/source_lock.json',
    '.github/workflows/dot-f07-link-evidence-20261031.yml',
    'docs/reader-total-progress/DOT_F07_LINK_EVIDENCE_20261031.md',
}

def need(ok, why):
    if not ok:
        raise ValueError(why)

def sha(b):
    return hashlib.sha256(b).hexdigest()

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

def safe(s):
    return not re.search(
        r'(?i)(?:authorization|password|access_token|client_secret)\s*["\x27]?\s*[:=]|\bBearer\s+\S+', s)

def main():
    need(os.environ.get('GITHUB_ACTIONS') == 'true', 'actions_only')
    OUT.mkdir(parents=True, exist_ok=False)
    result = dict(diagnostic_completed=False, errors=[], gate_changed=False,
                  product_rebuilt=False, artifact_code_executed=False,
                  audit_passed=False, F07_accepted=False, formal_count_changed=False,
                  full_log_parser_replay=False)
    try:
        source = git('rev-parse', 'HEAD').decode().strip()
        need(source == os.environ['GITHUB_SHA'], 'verifier_source')
        changed = set(git('diff', '--name-only', LOCK['base'], source).decode().splitlines())
        need(changed == SCOPE, 'exclusive_scope')
        oldbytes = (ROOT / OLD).read_bytes()
        need(oldbytes == git('show', LOCK['base'] + ':' + OLD), 'original_checker_unchanged')
        spec = importlib.util.spec_from_file_location('f07_original_checker', ROOT / OLD)
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        meta = old.api('/actions/runs/' + str(LOCK['run']))
        need(meta['head_sha'] == LOCK['source'] and meta['run_attempt'] == LOCK['attempt'], 'run_identity')
        jobs = old.api('/actions/runs/' + str(LOCK['run']) + '/attempts/1/jobs?per_page=100')['jobs']
        selected = [j for j in jobs if j['id'] == LOCK['job'] and j['name'] == 'windows']
        need(len(selected) == 1 and selected[0]['conclusion'] == 'success', 'producer_job')
        artifacts = old.api('/actions/runs/' + str(LOCK['run']) + '/artifacts?per_page=100')['artifacts']
        selected = [a for a in artifacts if a['id'] == LOCK['artifact'] and a['name'] == LOCK['name']]
        need(len(selected) == 1, 'artifact_identity')
        art = selected[0]
        need(not art['expired'] and art['size_in_bytes'] == LOCK['bytes'] and
             art['digest'] == 'sha256:' + LOCK['sha256'] and
             art['workflow_run']['id'] == LOCK['run'] and
             art['workflow_run']['head_sha'] == LOCK['source'], 'artifact_identity')
        raw = old.download(art)
        need(len(raw) == LOCK['bytes'] and sha(raw) == LOCK['sha256'], 'artifact_bytes')
        files = old.readzip(raw)
        binding = json.loads(old.txt(files, 'binding.json'))
        need((binding['source'], binding['product'], binding['sdk'], binding['run'],
              binding['attempt'], binding['platform']) ==
             (LOCK['source'], LOCK['product'], LOCK['sdk'], str(LOCK['run']),
              str(LOCK['attempt']), 'windows'), 'binding_identity')
        # Preserve the original inventory contract, not a new guessed member set.
        need(set(binding['files']) == set(files) - {'binding.json'}, 'inventory')
        for name, pin in binding['files'].items():
            need(pin == dict(bytes=len(files[name]), sha256=sha(files[name])), 'file_hash')
        for name, body in files.items():
            if name.endswith(('.log', '.json', '.txt', '.h', '.map')):
                need(all(safe(line) for line in body.decode('utf-8', 'replace').splitlines()),
                     'sensitive_input')
        (OUT / 'windows-original.zip').write_bytes(raw)
        lograw = files['host-build.log']
        log = lograw.decode('utf-8', 'strict')
        lines = log.splitlines()
        command = json.loads(old.txt(files, 'host-build.command.json'))
        mapping = old.txt(files, 'host.map')
        targets = binding['targets']
        # Keep ALL Searching/Loaded contexts before applying any SQLite member filter.
        searches = list(re.finditer(r'(?mi)^\s*Searching\s+(.+?\.lib):\s*$', log))
        blocks = []
        for index, match in enumerate(searches):
            end = searches[index+1].start() if index+1 < len(searches) else len(log)
            start_line = log.count('\n', 0, match.start()) + 1
            blocks.append(dict(start_line=start_line,
                               end_line=log.count('\n', 0, end) + 1,
                               searching=match.group(1),
                               text=log[match.start():end]))
        related = [dict(line=index, text=line) for index, line in enumerate(lines, 1)
                   if re.search(r'(?i)Searching|Loaded|sqlite|VERBOSE:LIB', line)]
        loaded = []
        refusal = None
        try:
            loaded = old.windows_loaded_sqlite(files, targets)
        except old.Refused as error:
            refusal = str(error)
        # Observe the original evaluator too. A failure is preserved, never weakened.
        original_result = None
        original_refusal = None
        try:
            original_result = old.evaluate(files, 'windows', LOCK['source'],
                                           str(LOCK['run']), str(LOCK['attempt']))
        except old.Refused as error:
            original_refusal = str(error)
        raw_loaded_rows = [dict(line=index, text=line) for index, line in enumerate(lines, 1)
                           if re.search(r'(?i)Loaded', line)]
        projected_matches = []
        for block in blocks:
            for archive, member in re.findall(
                    r'(?mi)^\s*Loaded\s+(.+?\.lib)\(\s*([^)]+)\s*\)\s*$', block['text']):
                if member.strip().lower() in ('sqlite3.c.obj', 'sqlite3.c.o'):
                    projected_matches.append(dict(searching=block['searching'],
                                                  archive=archive, member=member.strip()))
        count = len({(m['searching'].casefold(), m['member'].casefold())
                     for m in projected_matches})
        if refusal == 'provider_link_identity':
            classification = 'path_identity_mismatch'
        elif refusal == 'provider_loaded_ambiguous':
            classification = 'zero_matching_provider_evidence' if count == 0 else 'multiple_matching_provider_evidence'
        elif refusal is None:
            classification = 'original_loaded_parser_passed_not_F07_acceptance'
        else:
            classification = 'original_parser_refusal'
        map_facts = {}
        for symbol in ('sqlite3_open_v2', 'sqlite3_prepare_v2', 'sqlite3_sourceid'):
            owners = old.winowners(mapping, symbol)
            map_facts[symbol] = dict(owners=owners,
                allowed_archive_basename_matches=[
                    dict(owner=owner, keys=[key for key in ('product', 'sdk')
                        if old.owned_by(owner, targets[key], 'windows')]) for owner in owners])
        result.update(diagnostic_completed=True, classification=classification,
            full_log_parser_replay=True, source=LOCK['source'], product=LOCK['product'],
            sdk=LOCK['sdk'], producer_run=LOCK['run'], producer_attempt=LOCK['attempt'],
            producer_job=LOCK['job'], artifact=dict(id=art['id'], bytes=len(raw), sha256=sha(raw)),
            original_checker_sha256=sha(oldbytes),
            host_log=dict(bytes=len(lograw), sha256=sha(lograw), lines=len(lines),
                encoding='utf-8-strict', crlf=lograw.count(b'\r\n'), lf=lograw.count(b'\n')),
            command=command, command_sha256=sha(files['host-build.command.json']),
            map_sha256=sha(files['host.map']), map_facts=map_facts,
            original_loaded_parser=dict(refusal=refusal, returned=loaded),
            original_evaluator=dict(refusal=original_refusal, returned=original_result),
            searching_blocks=len(blocks), raw_loaded_rows=len(raw_loaded_rows),
            projected_sqlite_matches=projected_matches,
            evidence_missing=(count == 0),
            negative_controls_executed=False,
            limitation='Static original Windows profile only; no live-host or six-platform qualification.')
        (OUT / 'line-evidence.json').write_text(json.dumps(dict(
            relevant_lines=related, searching_blocks=blocks, loaded_rows=raw_loaded_rows),
            indent=2) + '\n')
        for name in ('host-build.log', 'host-build.command.json', 'host.map', 'binding.json'):
            (OUT / name).write_bytes(files[name])
    except Exception as error:
        result['errors'].append(str(error) if isinstance(error, (ValueError, KeyError)) else type(error).__name__)
    result.update(verifier_source=os.environ['GITHUB_SHA'],
                  verifier_run=os.environ['GITHUB_RUN_ID'],
                  verifier_attempt=os.environ['GITHUB_RUN_ATTEMPT'])
    (OUT / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print('F07_FULL_LINK_DIAGNOSTIC ' + json.dumps(result), flush=True)
    if not result['diagnostic_completed']:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
