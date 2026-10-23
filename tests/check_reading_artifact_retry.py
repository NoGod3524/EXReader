#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fake gh subprocess protocol checks; no downloads or SDK/performance credit."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from check_parallel_integration import download_artifact_zip
from prepare_reading_release import download


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('Run artifact transport protocol checks in Actions')
    checks = []
    command = ['gh', 'api', 'repos/synthetic/protocol/actions/artifacts/456/zip']
    payload = b'synthetic ZIP transport bytes\x00\xff'

    def passed(name):
        checks.append(name)

    def failure(status, parenthesized=False):
        message = ('gh: Service Unavailable (HTTP %d)\n' if parenthesized else 'gh: HTTP %d\n') % status
        return subprocess.CalledProcessError(1, command, stderr=message.encode())

    def observe(effect, operation=None):
        log = io.StringIO()
        with patch.dict(os.environ, GITHUB_REPOSITORY='synthetic/protocol'):
            with patch('check_parallel_integration.subprocess.run', side_effect=effect) as process, \
                 patch('check_parallel_integration.time.sleep') as sleep, \
                 patch('sys.stdout', log), patch('sys.stderr', io.StringIO()):
                try:
                    result, error = (operation or (lambda: download_artifact_zip(456)))(), None
                except (subprocess.SubprocessError, OSError, ValueError) as caught:
                    result, error = None, caught
        for call in process.call_args_list:
            assert call.args == (command,)
            assert call.kwargs['timeout'] == 120 and call.kwargs['check'] is True
            assert call.kwargs['stderr'] == subprocess.PIPE
        return result, error, process.call_count, [call.args[0] for call in sleep.call_args_list], log.getvalue()

    complete = subprocess.CompletedProcess(command, 0, stdout=payload)
    result, error, calls, waits, _ = observe([complete])
    assert result == payload and error is None and calls == 1 and waits == []
    passed('first_success_exact_binary_bytes')

    for status in (429, 502, 503, 504):
        for parenthesized in (False, True):
            result, error, calls, waits, log = observe([failure(status, parenthesized), complete])
            assert result == payload and error is None and calls == 2 and waits == [2]
            retry = json.loads(log)['artifact_retry']
            assert retry == {'artifact_id': 456, 'attempt': 1, 'status': status, 'delay_seconds': 2}
            passed('http_%d_%s_then_success' % (status, 'parenthesized' if parenthesized else 'plain'))

    result, error, calls, waits, _ = observe([failure(503), failure(504), complete])
    assert result == payload and error is None and calls == 3 and waits == [2, 4]
    passed('third_attempt_success_with_bounded_waits')

    for status in (429, 502, 503, 504):
        errors = [failure(status) for _ in range(3)]
        result, error, calls, waits, _ = observe(errors)
        assert result is None and error is errors[-1] and calls == 3 and waits == [2, 4]
        passed('http_%d_exhausted_preserves_last_error' % status)

    for status in (400, 401, 403, 404, 500):
        original = failure(status)
        result, error, calls, waits, _ = observe([original, complete])
        assert result is None and error is original and calls == 1 and waits == []
        passed('http_%d_no_retry' % status)

    for message in (b'authentication failed\n', b'HTTP 503\n', b'gh: HTTP 5030\n'):
        original = subprocess.CalledProcessError(1, command, stderr=message)
        _, error, calls, waits, _ = observe([original, complete])
        assert error is original and calls == 1 and waits == []
        passed('non_http_or_non_gh_failure_no_retry_' + str(len(checks)))

    for original in (subprocess.TimeoutExpired(command, 120), OSError('synthetic missing gh')):
        _, error, calls, waits, _ = observe([original, complete])
        assert error is original and calls == 1 and waits == []
        passed('timeout_or_spawn_failure_no_retry_' + str(len(checks)))

    stream = io.BytesIO(b'old bytes that must disappear')
    writes = 0
    def partial_then_success(args, stdout, **kwargs):
        nonlocal writes
        writes += 1
        stdout.write(b'partial invalid response' if writes == 1 else payload)
        if writes == 1:
            raise failure(503)
        return subprocess.CompletedProcess(args, 0)
    result, error, calls, waits, _ = observe(partial_then_success, lambda: download_artifact_zip(456, stream))
    assert result is None and error is None and calls == 2 and waits == [2] and stream.getvalue() == payload
    passed('partial_stream_reset_before_retry')

    item = {'id': 456, 'digest': 'sha256:' + hashlib.sha256(payload).hexdigest()}
    result, error, calls, waits, _ = observe([failure(503), complete], lambda: download(item))
    assert result == payload and error is None and calls == 2 and waits == [2]
    passed('prepare_recovers_then_checks_original_digest')
    bad = dict(item, digest='sha256:' + '0' * 64)
    _, error, calls, waits, _ = observe([failure(503), complete], lambda: download(bad))
    assert isinstance(error, ValueError) and 'digest changed' in str(error) and calls == 2 and waits == [2]
    passed('prepare_wrong_digest_after_retry_still_refused')

    print(json.dumps({'artifact_retry_protocol': True, 'passed': True, 'checks': len(checks), 'names': checks,
                      'real_artifact_downloads': 0, 'sdk_credit': 0, 'performance_credit': 0}))


if __name__ == '__main__':
    main()
