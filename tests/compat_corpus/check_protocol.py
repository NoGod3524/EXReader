#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only protocol self-tests; generated fixtures never count as real corpus."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('compat_protocol', ROOT / 'tools/compat_corpus/protocol.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def entry(name='book.txt', kind='real'):
    return {'id': name, 'path': name, 'sha256': '1' * 64, 'bytes': 15,
            'format': 'txt', 'variant': 'txt', 'kind': kind, 'scope': 'supported',
            'source': {'url': 'https://example.org/book.txt', 'creator': 'Fixture creator', 'license': 'MIT',
                       'origin': 'published_document' if kind == 'real' else 'original_test_fixture',
                       'permission': {'redistribution': True, 'scope': 'MIT worldwide redistribution',
                                      'reviewed_by': 'self-test only', 'evidence_url': 'https://example.org/LICENSE',
                                      'evidence_path': 'rights/LICENSE', 'evidence_sha256': '2' * 64}},
            'expected': {'status': 0, 'complete': True},
            'capabilities': {'open': 'complete', 'render': 'complete', 'extract': 'complete', 'save': 'not_evaluated'},
            'save_reason': 'Document checker does not save'}


def manifest(item=None):
    item = item or entry()
    return {'schema': 1, 'dataset_id': 'protocol-selftest', 'complete': True, 'targets': p.TARGETS.copy(),
            'selection': {'method': 'Fixed original test input', 'engine_results_used': False,
                          'candidate_ids': [item['id']], 'excluded': []}, 'files': [item]}


def check(binary, output):
    names = []

    def passed(name):
        names.append(name)

    def rejects(name, modify):
        value = manifest()
        modify(value)
        try:
            p.validate(value)
        except ValueError:
            passed(name)
        else:
            raise AssertionError(name)

    value = manifest()
    inventory = p.validate(value)
    assert inventory['real_supported']['txt'] == 1 and inventory['shortfall']['txt'] == 29
    passed('positive_predeclared_rights_reviewed_manifest')
    rejects('missing_source', lambda m: m['files'][0].pop('source'))
    rejects('missing_permission', lambda m: m['files'][0]['source'].pop('permission'))
    rejects('unconfirmed_redistribution', lambda m: m['files'][0]['source']['permission'].update(redistribution=False))
    rejects('missing_license_proof_hash', lambda m: m['files'][0]['source']['permission'].pop('evidence_sha256'))
    rejects('missing_expectations', lambda m: m['files'][0].pop('expected'))
    rejects('missing_capability', lambda m: m['files'][0]['capabilities'].pop('extract'))
    rejects('save_claim_not_measured', lambda m: m['files'][0]['capabilities'].update(save='complete'))
    rejects('synthetic_presented_as_real', lambda m: m['files'][0]['source'].update(origin='original_test_fixture'))
    rejects('filtered_candidate', lambda m: m['selection']['candidate_ids'].append('dropped-case'))
    rejects('filtered_failure', lambda m: m['selection']['excluded'].append(
        {'id': 'dropped-case', 'reason': 'engine_failed', 'evidence': 'observed failure'}))
    rejects('post_observation_selection', lambda m: m['selection'].update(engine_results_used=True))
    rejects('target_reduced', lambda m: m['targets'].update(pdf=122))
    rejects('extension_counted_as_new_format', lambda m: m['files'][0].update(format='xhtml'))
    rejects('missing_input_hash', lambda m: m['files'][0].pop('sha256'))
    rejects('path_escape', lambda m: m['files'][0].update(path='../book.txt'))
    rejects('absolute_path', lambda m: m['files'][0].update(path='/book.txt'))
    rejects('source_without_https', lambda m: m['files'][0]['source'].update(url='http://example.org/book.txt'))
    rejects('unexpected_rejection_in_supported_scope', lambda m: m['files'][0]['expected'].update(status=11, complete=False))

    def duplicate(m):
        other = deepcopy(m['files'][0])
        other.update(id='alias', path='alias.txt')
        m['files'].append(other)
        m['selection']['candidate_ids'].append('alias')
    rejects('duplicate_content_cannot_inflate_targets', duplicate)
    for fmt, variant, suffix in [('html', 'xhtml', 'xhtml'), ('mobi', 'kf8', 'azw3')]:
        item = entry('variant.' + suffix)
        item.update(format=fmt, variant=variant)
        assert p.validate(manifest(item))['real_supported'][fmt] == 1
    passed('canonical_formats_and_content_variants')
    synthetic = manifest(entry(kind='synthetic'))
    assert p.validate(synthetic)['real_supported']['txt'] == 0
    assert not p.acceptance(synthetic, p.validate(synthetic), {'passed': 1})['pipeline_accepted']
    passed('synthetic_never_satisfies_real_target')
    assert not p.acceptance(value, inventory, {'passed': 1})['pipeline_accepted']
    passed('insufficient_real_counts_refused')
    enough = deepcopy(inventory)
    enough['shortfall'] = dict.fromkeys(p.TARGETS, 0)
    assert p.acceptance(value, enough, {'passed': 1})['pipeline_accepted']
    assert not p.acceptance(value, enough, {'passed': 1})['accepted']
    passed('pipeline_acceptance_does_not_grant_full_fidelity_or_save_acceptance')
    assert not p.acceptance(value, enough, {})['pipeline_accepted']
    assert not p.acceptance(value, enough, {'timeout': 1})['pipeline_accepted']
    passed('filtered_result_and_timeout_refused')

    # Use the existing checker in real native processes, retaining all generated evidence in the artifact.
    assets = output / 'assets'
    assets.mkdir()
    good = assets / 'book.txt'
    good.write_text('A complete original self-test publication.', encoding='utf-8')
    proof_path = assets / 'rights/LICENSE'
    proof_path.parent.mkdir()
    proof_path.write_bytes((ROOT / 'LICENSE').read_bytes())
    item = entry(kind='synthetic')
    item.update(bytes=good.stat().st_size, sha256=p.digest(good))
    item['source']['permission']['evidence_sha256'] = p.digest(proof_path)
    synthetic = manifest(item)
    p.verify_assets(synthetic, assets)
    passed('positive_asset_and_rights_hash_verification')
    original = good.read_bytes()
    good.write_bytes(original + b'changed')
    try:
        p.verify_assets(synthetic, assets)
    except ValueError:
        passed('changed_input_refused')
    else:
        raise AssertionError('changed input')
    good.write_bytes(original)
    saved_proof = proof_path.read_bytes()
    proof_path.write_bytes(saved_proof + b'changed')
    try:
        p.verify_assets(synthetic, assets)
    except ValueError:
        passed('changed_permission_evidence_refused')
    else:
        raise AssertionError('changed rights proof')
    proof_path.write_bytes(saved_proof)
    assert p.fetch('https://example.org/book.txt', good, item['sha256'], item['bytes']) == 'verified_existing'
    passed('collection_resume_checks_existing_asset_hash')
    try:
        p.fetch('https://example.org/book.txt', good, '0' * 64, item['bytes'])
    except ValueError:
        passed('collection_resume_refuses_changed_asset')
    else:
        raise AssertionError('changed collected input')

    # Exercise bounded download and partial preservation without collecting external publications.
    import io
    class Opener:
        def open(self, *args, **kwargs):
            return io.BytesIO(b'original test bytes')
    with patch.object(p.urllib.request, 'build_opener', return_value=Opener()):
        downloaded = assets / 'downloaded.txt'
        data = b'original test bytes'
        assert p.fetch('https://example.org/book.txt', downloaded, p.sha_bytes(data), len(data)) == 'downloaded'
        passed('bounded_collector_positive')
        for name, sha, size in [('hash-mismatch', '0' * 64, len(data)),
                                 ('byte-limit', p.sha_bytes(data), len(data) - 1)]:
            path = assets / (name + '.txt')
            try:
                p.fetch('https://example.org/book.txt', path, sha, size)
            except ValueError:
                assert not path.exists() and path.with_name(path.name + '.partial').exists()
                passed('collector_' + name + '_preserves_partial')
            else:
                raise AssertionError(name)

    checker_manifest = output / 'checker-manifest.json'
    p.write_json(checker_manifest, {'files': [item], 'target': 1, 'complete': True})
    source_sha = p.git('rev-parse', 'HEAD').decode().strip()
    def probe(name, expected_exit):
        with (output / (name + '.stdout')).open('wb') as stdout, (output / (name + '.stderr')).open('wb') as stderr:
            result = subprocess.run([sys.executable, str(ROOT / 'tools/check_corpus.py'), str(binary),
                str(ROOT / 'tests/fixtures/fonts/primary.ttf'), str(checker_manifest), str(output / name),
                '--root', str(assets), '--timeout', '60'], stdout=stdout, stderr=stderr, timeout=90)
        assert result.returncode == expected_exit, name
        return json.loads((output / name / 'summary.json').read_text())
    summary = probe('native-positive', 0)
    assert p.verify_summary(synthetic, summary, source_sha) == {'passed': 1}
    passed('native_checker_complete_process_reuse')
    filtered = deepcopy(summary)
    filtered['results'] = []
    try:
        p.verify_summary(synthetic, filtered, source_sha)
    except ValueError:
        passed('native_filtered_outcome_refused')
    else:
        raise AssertionError('filtered native result')
    changed = deepcopy(summary)
    changed['source_sha'] = '0' * 40
    try:
        p.verify_summary(synthetic, changed, source_sha)
    except ValueError:
        passed('cross_source_result_refused')
    else:
        raise AssertionError('cross source')
    changed_manifest = deepcopy(synthetic)
    changed_manifest['files'][0]['expected']['status'] = 11
    try:
        p.verify_summary(changed_manifest, summary, source_sha)
    except ValueError:
        passed('expectations_changed_after_observation_refused')
    else:
        raise AssertionError('expectation rewrite')
    stderr = output / 'native-positive/00000/stderr.log'
    stderr.write_bytes(stderr.read_bytes() + b'changed')
    try:
        p.verify_summary(synthetic, summary, source_sha)
    except ValueError:
        passed('changed_attachment_refused')
    else:
        raise AssertionError('changed attachment')

    bad = assets / 'invalid.epub'
    bad.write_bytes(b'Original invalid self-test document')
    bad_item = deepcopy(item)
    bad_item.update(id='invalid', path=bad.name, format='epub', variant='epub',
                    sha256=p.digest(bad), bytes=bad.stat().st_size)
    bad_manifest = manifest(bad_item)
    p.write_json(checker_manifest, {'files': [bad_item], 'target': 1, 'complete': True})
    summary = probe('native-retained-failure', 1)
    counts = p.verify_summary(bad_manifest, summary, source_sha)
    assert counts == {'unexpected_outcome': 1}
    assert not p.acceptance(bad_manifest, p.validate(bad_manifest), counts)['pipeline_accepted']
    passed('native_failure_retained_and_refused')

    # Registration is tied to the first committed version, including its capability expectations.
    pending_path = ROOT / 'tools/compat_corpus/manifest.json'
    additions = p.git('log', '--reverse', '--diff-filter=A', '--format=%H', 'HEAD', '--',
                      'tools/compat_corpus/manifest.json').decode().splitlines()
    assert additions
    seal = p.registered(pending_path, additions[0])
    assert seal['sha256'] == p.digest(pending_path)
    passed('committed_registration_anchor')
    if source_sha != additions[0]:
        try:
            p.registered(pending_path, source_sha)
        except ValueError:
            passed('new_registration_cannot_replace_original_anchor')
        else:
            raise AssertionError('replacement registration')
    # A real independent Git history proves both prior-byte and first-registration guards.
    with tempfile.TemporaryDirectory(prefix='compat-registration-') as directory:
        temporary_root = Path(directory)
        def tempgit(*args):
            return subprocess.run(['git', '-C', str(temporary_root), *args], check=True,
                                  capture_output=True).stdout.decode().strip()
        tempgit('init')
        tempgit('config', 'user.name', 'Protocol self-test')
        tempgit('config', 'user.email', 'protocol-selftest@example.invalid')
        temporary_manifest = temporary_root / 'manifest.json'
        p.write_json(temporary_manifest, synthetic)
        tempgit('add', 'manifest.json')
        tempgit('commit', '-m', 'Register expectations before execution')
        original_commit = tempgit('rev-parse', 'HEAD')
        with patch.object(p, 'ROOT', temporary_root):
            assert p.registered(temporary_manifest, original_commit)['commit'] == original_commit
            passed('independent_registration_positive')
            rewritten = deepcopy(synthetic)
            rewritten['files'][0]['expected']['status'] = 11
            p.write_json(temporary_manifest, rewritten)
            tempgit('add', 'manifest.json')
            tempgit('commit', '-m', 'Post-observation expectation rewrite')
            for name, commit in [('prior_expectation_bytes', original_commit),
                                 ('replacement_registration', tempgit('rev-parse', 'HEAD'))]:
                try:
                    p.registered(temporary_manifest, commit)
                except ValueError:
                    passed('git_' + name + '_refused')
                else:
                    raise AssertionError(name)
    report = {'schema': 1, 'passed': True, 'checks': names, 'count': len(names), 'source_sha': source_sha,
              'run_id': os.environ['GITHUB_RUN_ID'], 'real_documents_collected': 0, 'corpus_accepted': False}
    p.write_json(output / 'checks.json', report)
    print(json.dumps({'checks': len(names), 'passed': True, 'corpus_accepted': False}))


if __name__ == '__main__':
    p.cloud_only()
    destination = Path(sys.argv[2]).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    check(Path(sys.argv[1]).resolve(), destination)
