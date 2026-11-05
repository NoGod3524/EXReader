"""Small Actions-only regressions for the four repaired evidence boundaries."""
import copy
import hashlib
import os
from pathlib import Path
import tempfile
import bundle_copy
import identity
import summary
import verify


def rejected(name, operation):
    try:
        operation()
    except ValueError:
        print('REFUSED', name)
    else:
        raise AssertionError('accepted evidence mutation: ' + name)


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    implementation = dict(sha='a' * 40, run_id='123', attempt='1')
    identity.same_implementation(implementation, implementation)
    rejected('foreign-attempt', lambda: identity.same_implementation(dict(implementation, attempt='2'), implementation))
    raw = b'authenticated original ZIP bytes'
    meta = dict(size_in_bytes=len(raw), digest='sha256:' + hashlib.sha256(raw).hexdigest())
    identity.validate_download(meta, raw)
    rejected('wrong-ZIP-size', lambda: identity.validate_download(dict(meta, size_in_bytes=1), raw))
    rejected('wrong-ZIP-digest', lambda: identity.validate_download(dict(meta, digest='sha256:' + '0' * 64), raw))
    meta.update(expired=False, expires_at='2035-01-01T00:00:00Z', workflow_run=dict(id=123, head_sha='a' * 40))
    identity.metadata(meta, 'a' * 40, 123)
    rejected('foreign-artifact-source', lambda: identity.metadata(meta, 'b' * 40, 123))
    rejected('past-expiry', lambda: identity.metadata(dict(meta, expires_at='2020-01-01T00:00:00Z'), 'a' * 40, 123))
    with tempfile.TemporaryDirectory(prefix='s05-chain-') as temporary:
        app = Path(temporary) / 'Evidence.app';app.mkdir()
        executable = app / 'EXReaderHost';executable.write_bytes(b'unchanged executable')
        resource = app / 'Book.txt';resource.write_bytes(b'original resource')
        original = bundle_copy.snapshot(app)
        bundle_copy.same(bundle_copy.snapshot(app), original)
        resource.write_bytes(b'replaced resource')
        rejected('resource-replaced-after-copy', lambda: bundle_copy.same(bundle_copy.snapshot(app), original))
        resource.write_bytes(b'original resource');executable.chmod(0o700)
        changed = bundle_copy.snapshot(app)
        if changed != original:
            rejected('observed-stage-mode-changed', lambda: bundle_copy.same(changed, original))
        else:
            executable.chmod(0o600)
            rejected('observed-stage-mode-changed', lambda: bundle_copy.same(bundle_copy.snapshot(app), original))
        # These chmod calls mutate a generated regression fixture only. The
        # producer intake, staging, restore and smoke never chmod a real app.
        assert bundle_copy.running_program(42, '42 ' + str(executable), executable)
        assert not bundle_copy.running_program(42, '42 /wrong/EXReaderHost', executable)
        assert not bundle_copy.running_program(42, '43 ' + str(executable), executable)
    assert verify.signing_established(dict(state='signed', bundle_sealed=True, verify=True))
    assert not verify.signing_established(dict(state='signed', bundle_sealed=False, verify=True))
    assert not verify.signing_established(dict(state='ad-hoc', bundle_sealed=True, verify=True))
    found = dict(fixture_checks=[dict(implementation=implementation)], producer_source=[], results=[])
    for device in ('iphone', 'ipad'):
        source = dict(implementation=implementation, chosen={device: {}}, designation={}, run={}, artifact={}, eligible=True, blocked_by=[])
        found['producer_source'].append(source)
        for smoke in (False, True):
            found['results'].append(dict(device_class=device, mode='fixture', sources=dict(implementation=implementation), install_smoke=dict(requested=smoke)))
        found['results'].append(dict(device_class=device, mode='producer',
                                    sources=dict(implementation=implementation, producer={key: source[key] for key in ('designation', 'run', 'artifact', 'eligible', 'blocked_by')}),
                                    install_smoke=dict(requested=True)))
    summary.validate_unique(found, implementation)
    duplicate = copy.deepcopy(found);duplicate['results'].append(duplicate['results'][-1])
    rejected('duplicate-device-result', lambda: summary.validate_unique(duplicate, implementation))
    missing = copy.deepcopy(found);missing['producer_source'].pop()
    rejected('missing-device-intake', lambda: summary.validate_unique(missing, implementation))
    foreign = copy.deepcopy(found);foreign['results'][0]['sources']['implementation']['attempt'] = '2'
    rejected('foreign-result-attempt', lambda: summary.validate_unique(foreign, implementation))
    print('S05 evidence-chain regressions passed')


if __name__ == '__main__':
    main()
