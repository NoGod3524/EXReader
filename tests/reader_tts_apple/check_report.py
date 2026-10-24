# SPDX-License-Identifier: MIT
"""Shared verification of one platform report produced inside GitHub Actions.

The report is produced by the installed consumer (and, on macOS, by the
platform-neutral logic suite). Nothing here builds or parses binaries: it only
checks the identity, the per-case names, and the pass/fail/pending policy.
"""
import hashlib
import json
import os

# Cases that must exist and pass on every platform. A report that silently drops
# one of them is rejected even when the surviving counts look healthy.
REQUIRED_BY_KIND = {
    'logic': [
        'create.default-config',
        'create.lowered-cap-enforced',
        'create.no-installed-voice-is-service-unavailable',
        'speak.started-range-terminal-ordering',
        'speak.utf16-offsets-convert-to-utf8',
        'speak.range-drops-unusable-offsets',
        'speak.invalid-utf8-rejected',
        'close.retains-the-terminal-event',
        'destroy.before-closed-is-busy',
        'owner.observe-from-another-thread',
        'events.queue-exhaustion-is-limit-then-recovers',
    ],
    'probe': [
        'probe.create-ok',
        'probe.state-after-create',
        'probe.voices-listed',
        'probe.rejects-zero-bytes',
        'probe.rejects-invalid-utf8',
        'probe.rejects-over-limit',
        'probe.observe-off-main-thread',
        'probe.handle-survived-foreign-destroy',
        'probe.close-idempotent',
        'probe.closed-state',
        'probe.destroy-clears-pointer',
    ],
}

# Speech cases may only be pending when the platform really has no audio route or
# no installed voice; the reason has to be recorded in the same report.
PENDING_ALLOWED = {
    'probe.voices-listed',
    'probe.speak-english-lifecycle',
    'probe.speak-english-callbacks',
    'probe.state-ready-after-finish',
    'probe.speak-chinese-emoji-lifecycle',
    'probe.range-byte-boundaries',
    'probe.range-advances',
    'probe.speak-named-voice',
    'probe.pause-resume',
    'probe.stop-after-pause',
    'probe.queue-replacement-busy',
    'probe.cancel-terminal-once',
    'probe.late-callback-isolation',
    'probe.pcm-wav-captured',
}

MINIMUM_LOGIC_CASES = 55


class ReportError(AssertionError):
    pass


def _require(condition, message):
    if not condition:
        raise ReportError(message)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def verify_identity(report, platform):
    _require(report.get('source_sha') == os.environ['GITHUB_SHA'], 'source_sha does not match GITHUB_SHA')
    _require(int(report.get('run_id', 0)) == int(os.environ['GITHUB_RUN_ID']), 'run_id mismatch')
    _require(int(report.get('attempt', 0)) == int(os.environ['GITHUB_RUN_ATTEMPT']), 'attempt mismatch')
    _require(report.get('platform') == platform, 'platform mismatch: %r' % (report.get('platform'),))
    _require(report.get('schema') == 1, 'unexpected report schema')


def verify_checks(report, kind):
    checks = report.get('checks') or []
    _require(checks, 'report has no named checks')
    names = [check['name'] for check in checks]
    _require(len(names) == len(set(names)), 'duplicate check names in report')
    statuses = {check['name']: check['status'] for check in checks}
    counts = {'pass': 0, 'fail': 0, 'pending': 0}
    for check in checks:
        _require(check['status'] in counts, 'unknown status %r' % (check['status'],))
        counts[check['status']] += 1
        if check['status'] == 'pending':
            _require(check['name'] in PENDING_ALLOWED,
                     'unexpected pending case %s' % check['name'])
            _require(check.get('detail'), 'pending case %s has no recorded reason' % check['name'])
    _require(counts['fail'] == 0, 'failing cases: %s' % (report.get('counts'),))
    declared = report.get('counts') or {}
    for key, value in counts.items():
        _require(declared.get(key) == value,
                 'declared %s count %r does not match the cases (%d)' % (key, declared.get(key), value))
    for required in REQUIRED_BY_KIND[kind]:
        _require(required in statuses, 'required case missing: %s' % required)
        status = statuses[required]
        _require(status == 'pass' or (status == 'pending' and required in PENDING_ALLOWED),
                 'required case did not pass: %s (%s)' % (required, status))
    if kind == 'logic':
        _require(counts['pass'] >= MINIMUM_LOGIC_CASES,
                 'logic suite has only %d passing cases' % counts['pass'])
    if counts['pending']:
        _require(report.get('speech_available') is False, 'pending speech cases with speech_available=true')
        _require(report.get('speech_note'), 'pending speech cases without a recorded note')
    return counts


def verify_consumer(report, consumer_path):
    actual = sha256_file(consumer_path)
    _require(report.get('consumer_sha256') == actual,
             'consumer_sha256 mismatch: report %r file %r' % (report.get('consumer_sha256'), actual))
    return actual


def load(path):
    with open(path, 'r', encoding='utf-8') as handle:
        return json.load(handle)
