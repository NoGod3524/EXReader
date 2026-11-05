# SPDX-License-Identifier: MIT
"""Actions-only rejection cases exercising the same validators as real evidence."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import warnings
import zipfile

from evidence import archive_files, strict_json, verify_artifact, verify_binary, verify_inventory, verify_job, verify_probe, verify_zip_bytes
from relaylib import HERE, Refused, load_expected


def selftest(identity):
    def rejected(name, function):
        try:
            function()
        except (Refused, ValueError, KeyError, TypeError):
            print('selftest rejected:', name)
            return
        raise AssertionError('selftest: %s was NOT rejected' % name)

    job = dict(id=1, name='build (Linux)', status='completed', conclusion='success', head_sha=identity['source_sha'],
               run_id=int(identity['run_id']), run_attempt=int(identity['attempt']), labels=['ubuntu-22.04'])
    verify_job(identity, job, job['name'], 'Linux')
    for field, value in [('status', 'in_progress'), ('conclusion', 'failure'), ('run_id', 0), ('run_attempt', 0),
                         ('head_sha', '0' * 40), ('labels', ['windows-2022'])]:
        changed = dict(job, **{field: value})
        rejected('API job ' + field, lambda v=changed: verify_job(identity, v, job['name'], 'Linux'))
    artifact = dict(id=2, name='relay-test', expired=False, size_in_bytes=3, digest='sha256:' + hashlib.sha256(b'abc').hexdigest(),
                    workflow_run=dict(head_sha=identity['source_sha'], id=int(identity['run_id'])), expires_at='2099-01-01T00:00:00Z')
    verify_artifact(identity, artifact, artifact['name'])
    verify_zip_bytes(b'abc', artifact)
    for field, value in [('expired', True), ('size_in_bytes', 0), ('digest', ''), ('expires_at', '2000-01-01T00:00:00Z'),
                         ('workflow_run', dict(head_sha=identity['source_sha'], id=0)), ('workflow_run', dict(head_sha='0' * 40, id=int(identity['run_id'])))]:
        changed = dict(artifact, **{field: value})
        rejected('API artifact ' + field, lambda v=changed: verify_artifact(identity, v, artifact['name']))
    rejected('ZIP bytes tampered', lambda: verify_zip_bytes(b'abd', artifact))
    rejected('ZIP length differs', lambda: verify_zip_bytes(b'abcd', artifact))
    rejected('duplicate JSON report key', lambda: strict_json('{"accepted":false,"accepted":true}'))

    def zip_check(entries, function=archive_files):
        data = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(data, 'w') as archive:
                for name, body in entries:
                    archive.writestr(name, body)
        with zipfile.ZipFile(io.BytesIO(data.getvalue())) as archive:
            return function(archive)

    basic = [('result.json', '{}')]
    zip_check(basic)
    binary = basic + [('bin/consumer', b'consumer')]
    binary_sha = hashlib.sha256(b'consumer').hexdigest()
    zip_check(binary, lambda a: verify_binary(a, 'bin/consumer', binary_sha))
    rejected('actual consumer binary tampered', lambda: zip_check(binary, lambda a: verify_binary(a, 'bin/consumer', '0' * 64)))
    for name, entries in [('duplicate ZIP report', basic + basic), ('nested report', basic + [('other/result.json', '{}')]),
                          ('missing report', [('other.json', '{}')]), ('traversal ZIP member', basic + [('../escape', '')]),
                          ('backslash ZIP member', basic + [('tree\\x', '')]), ('database ZIP member', basic + [('tree/x.sqlite', '')])]:
        rejected(name, lambda e=entries: zip_check(e))
    link = zipfile.ZipInfo('tree/link')
    link.create_system = 3
    link.external_attr = 0o120777 << 16
    rejected('symlink ZIP member', lambda: zip_check(basic + [(link, 'target')]))

    content = b'original'
    file_sha = hashlib.sha256(content).hexdigest()
    inv_digest = hashlib.sha256(('D\tdir\nF\t%d\t%s\tdir/book\n' % (len(content), file_sha)).encode()).hexdigest()
    inventory = dict(format='exr-relay-inventory-1', file_count=1, dir_count=1, total_bytes=len(content), digest=inv_digest,
                     dirs=['dir'], files=[dict(path='dir/book', bytes=len(content), sha256=file_sha)])
    raw = json.dumps(inventory).encode()
    peer = dict(inventory_sha256=hashlib.sha256(raw).hexdigest(), inventory_digest=inv_digest)
    entries = basic + [('inventory.json', raw), ('tree/dir/book', content)]
    def checked_inventory(archive, p=peer):
        return verify_inventory(archive, archive_files(archive), p)
    zip_check(entries, checked_inventory)
    rejected('raw tree altered', lambda: zip_check(entries[:-1] + [('tree/dir/book', b'changed!')], checked_inventory))
    rejected('raw tree missing', lambda: zip_check(entries[:-1], checked_inventory))
    rejected('raw tree extra', lambda: zip_check(entries + [('tree/dir/extra', b'x')], checked_inventory))
    rejected('inventory digest forged', lambda: zip_check(entries, lambda a: verify_inventory(a, archive_files(a), dict(peer, inventory_digest='0' * 64))))
    duplicated = copy.deepcopy(inventory)
    duplicated['files'].append(copy.deepcopy(duplicated['files'][0]))
    raw_duplicate = json.dumps(duplicated).encode()
    rejected('duplicate inventory member', lambda: zip_check(basic + [('inventory.json', raw_duplicate), entries[-1]],
             lambda a: verify_inventory(a, archive_files(a), dict(peer, inventory_sha256=hashlib.sha256(raw_duplicate).hexdigest()))))

    expected = load_expected()
    report = dict(failures=0, checks=[dict(name='real probe check', **{'pass': True})], cases=copy.deepcopy(expected['cases']),
                  receiver_found=17, receiver_ambiguous=1, receiver_mislocated=0, network_pulled=31, metadata_projected=4,
                  cancelled_attempts=1, reopens=3)
    verify_probe(report, 'receive', expected)
    for field, value in [('receiver_mislocated', 1), ('cases', []), ('checks', []), ('reopens', 0)]:
        rejected('raw SDK report ' + field, lambda f=field, v=value: verify_probe(dict(report, **{f: v}), 'receive', expected))

    # Rejection must occur in the receiving path, before any service is started,
    # not merely mark the eventual report red after serving suspect bytes.
    from relay import Checks, load_package
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / 'transport.tsv').write_bytes(b'transport')
        (root / 'inventory.json').write_bytes(b'inventory')
        valid = dict(identity, direction='linux-to-windows', stage='send', os='Linux',
                     expected_sha256=hashlib.sha256((HERE / 'expected.json').read_bytes()).hexdigest(),
                     transport_sha256=hashlib.sha256(b'transport').hexdigest(), inventory_sha256=hashlib.sha256(b'inventory').hexdigest())
        for field, value in [('source_sha', '0' * 40), ('run_id', '0'), ('attempt', '0'), ('os', 'Windows'), ('transport_sha256', '0' * 64)]:
            (root / 'identity.json').write_text(json.dumps(dict(valid, **{field: value})), encoding='utf-8')
            rejected('receive rejects peer ' + field, lambda: load_package(root, identity, 'linux-to-windows', 'send', 'unused-tool', Checks()))
        (root / 'identity.json').write_text(json.dumps(valid), encoding='utf-8')
        with patch('relay.tool', return_value=SimpleNamespace(returncode=1, stderr='rejected', stdout='MISMATCH')), \
             patch('relay.canonical_inventory', return_value=b'inventory'), patch('relay.clone_tree'):
            rejected('native inventory failure stops serving', lambda: load_package(root, identity, 'linux-to-windows', 'send', 'unused-tool', Checks()))
