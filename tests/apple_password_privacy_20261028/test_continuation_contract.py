#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import os
import hashlib
import http.client
import inspect
import json
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler
from contract import ROOT, sha
from continuation_contract import CASE, STAGES, case_name, verdict
from continuation_lifecycle import ContinuationLifecycle, LifecycleHTTPServer, atomic_result, seal_files, verify_lifecycle, write_unsealed
from fixture import fixture


def blocked_server(directory, lifecycle, release):
    entered = threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *unused): pass
        def do_GET(self):
            entered.set(); release.wait()
            (directory / 'checkpoints.json').write_bytes(b'final callback bytes')
            self.send_response(204); self.end_headers()
    server = LifecycleHTTPServer(('127.0.0.1', 0), Handler, lifecycle, None, [])
    serving = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.005), daemon=True); serving.start()
    client = socket.create_connection(server.server_address, timeout=2)
    client.sendall(b'GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
    if not entered.wait(2): raise RuntimeError('control callback did not enter')
    return server, serving, client


def timeout_child(directory):
    lifecycle = ContinuationLifecycle('macos', budget_seconds=2, drain_seconds=0.05)
    server, serving, client = blocked_server(directory, lifecycle, threading.Event())
    try:
        lifecycle.stop(server, serving)
        raise AssertionError('blocked writer was certified drained')
    except RuntimeError:
        receipt = lifecycle.receipt()
        if receipt['drained'] or not receipt['failed'] or receipt['active_handlers'] != 1:
            raise AssertionError('timeout receipt differs')
        write_unsealed(directory, 'a' * 40, 'macos', lifecycle)
        if (directory / 'result.json').exists(): raise AssertionError('normal manifest on timeout')
    finally:
        client.close()


class ContinuationControls(unittest.TestCase):
    def test_delayed_disconnected_callback_must_drain_before_final_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder); release = threading.Event()
            lifecycle = ContinuationLifecycle('macos', budget_seconds=5, drain_seconds=3)
            server, serving, client = blocked_server(directory, lifecycle, release)
            client.settimeout(0.02)
            with self.assertRaises(socket.timeout): client.recv(1)
            client.close()  # HTTP client departure is not callback completion.
            closed, errors = threading.Event(), []
            def stop():
                try: lifecycle.stop(server, serving)
                except Exception: errors.append('refused')
                finally: closed.set()
            stopping = threading.Thread(target=stop, daemon=True); stopping.start()
            try:
                self.assertTrue(lifecycle.admission_closed_event.wait(2))
                self.assertFalse(closed.wait(0.05))
                self.assertFalse((directory / 'checkpoints.json').exists())
            finally:
                release.set()
            self.assertTrue(closed.wait(3)); stopping.join(timeout=1)
            self.assertEqual(errors, []); self.assertTrue(lifecycle.drained)
            self.assertEqual(lifecycle.active, 0)
            proof = seal_files(directory)
            self.assertEqual(proof['checkpoints.json']['sha256'], hashlib.sha256(b'final callback bytes').hexdigest())

    def test_drain_timeout_exits_subprocess_with_only_unsealed_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            done = subprocess.run([sys.executable, __file__, '--timeout-child', folder], capture_output=True, timeout=5)
            self.assertEqual(done.returncode, 0, 'isolated drain timeout control failed')
            self.assertFalse((Path(folder) / 'result.json').exists())
            report = json.loads((Path(folder) / 'unsealed.json').read_text())
            self.assertFalse(report['accepted']); self.assertFalse(report['evidence_sealed'])
            self.assertFalse(report['sequence_complete']); self.assertFalse(report['full_f10_accepted'])
            self.assertTrue(report['lifecycle']['failed']); self.assertEqual(report['lifecycle']['active_handlers'], 1)
            self.assertEqual(report['source_sha'], 'a' * 40)

    def test_admission_fence_rejects_late_queued_handler_and_underflow(self):
        lifecycle = ContinuationLifecycle('macos'); lifecycle.close_admission()
        called = threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def handle(self): called.set()
        server = LifecycleHTTPServer(('127.0.0.1', 0), Handler, lifecycle, None, [])
        left, right = socket.socketpair()
        try:
            late = threading.Thread(target=server.process_request_thread, args=(left, ('local', 0)))
            late.start(); late.join(timeout=2)
            self.assertFalse(late.is_alive()); self.assertFalse(called.is_set())
            self.assertEqual((lifecycle.active, lifecycle.admitted, lifecycle.rejected), (0, 0, 1))
            with self.assertRaisesRegex(RuntimeError, '^lifecycle counter underflow$'): lifecycle.release()
            self.assertTrue(lifecycle.failed)
        finally:
            left.close(); right.close(); server.server_close()

    def test_tls_handshake_is_owned_even_with_zero_request_handlers(self):
        lifecycle = ContinuationLifecycle('macos', budget_seconds=4, drain_seconds=2)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server = LifecycleHTTPServer(('127.0.0.1', 0), BaseHTTPRequestHandler, lifecycle, context, [])
        serving = threading.Thread(target=server.serve_forever, daemon=True); serving.start()
        client = socket.create_connection(server.server_address, timeout=2)
        try:
            self.assertTrue(server.handshake_started.wait(2))
            self.assertEqual(lifecycle.active, 0)
            self.assertFalse(lifecycle.serving_stopped)
            lifecycle.stop(server, serving)
            self.assertTrue(lifecycle.serving_stopped); self.assertFalse(serving.is_alive())
        finally:
            client.close()

    def test_stalled_cleanup_and_expired_deadline_never_claim_success(self):
        release = threading.Event()
        class StalledServer:
            def close_owned_sockets(self): pass
            def shutdown(self): release.wait()
            def server_close(self): pass
        serving = threading.Thread(target=release.wait, daemon=True); serving.start()
        blocked = ContinuationLifecycle('macos', budget_seconds=1, drain_seconds=0.02)
        try:
            with self.assertRaisesRegex(RuntimeError, '^continuation drain incomplete$'):
                blocked.stop(StalledServer(), serving)
            self.assertFalse(blocked.serving_stopped); self.assertFalse(blocked.drained)
        finally:
            release.set(); serving.join(timeout=1)
        lifecycle = ContinuationLifecycle('iphone', budget_seconds=0.1, drain_seconds=0.05)
        before = time.monotonic()
        self.assertFalse(lifecycle.cleanup_command('certificate', [sys.executable, '-c', 'import time; time.sleep(60)']))
        self.assertLess(time.monotonic() - before, 3)
        self.assertFalse(lifecycle.cleanup_command('simulator-shutdown', [sys.executable, '-c', 'raise SystemExit(0)']))
        self.assertEqual(lifecycle.cleanup['simulator-shutdown'], 'not-attempted-deadline')
        with self.assertRaises(RuntimeError): verify_lifecycle(lifecycle.receipt(), 'iphone')

    def test_bounded_command_refuses_lingering_descendant_without_truncating_output(self):
        lifecycle = ContinuationLifecycle('macos', budget_seconds=5, drain_seconds=1)
        script = ('import os,sys,time; '
                  'sys.stdout.buffer.write(b"X" * (17 * 1024 * 1024)); sys.stdout.flush(); '
                  'pid=os.fork(); '
                  'time.sleep(60) if pid == 0 else None')
        started = time.monotonic()
        done = lifecycle.command([sys.executable, '-c', script], cap=3, check=False, max_capture=None)
        self.assertLess(time.monotonic() - started, 5)
        self.assertNotEqual(done.returncode, 0)
        self.assertTrue(lifecycle.failed)
        self.assertEqual(len(done.stdout), 17 * 1024 * 1024)
        self.assertEqual(hashlib.sha256(done.stdout).hexdigest(), hashlib.sha256(b'X' * (17 * 1024 * 1024)).hexdigest())

    def test_seal_streams_large_files_and_refuses_earlier_prefix_namespace_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder); large = directory / 'a-large'
            digest = hashlib.sha256()
            with large.open('wb') as file:
                for index in range(65):
                    data = bytes([index]) * (1024 * 1024); file.write(data); digest.update(data)
                file.write(b'boundary'); digest.update(b'boundary')
            (directory / 'z-last').write_bytes(b'last')
            proof = seal_files(directory)
            self.assertEqual(proof['a-large'], {'bytes': 65 * 1024 * 1024 + 8, 'sha256': digest.hexdigest()})
            def prefix_change():
                with large.open('r+b') as file: file.write(b'changed')
            with self.assertRaises(RuntimeError): seal_files(directory, between_passes=prefix_change)
            with self.assertRaises(RuntimeError): seal_files(directory,
                between_passes=lambda: (directory / 'new-file').write_bytes(b'late'))
            with self.assertRaises(RuntimeError): seal_files(directory,
                between_passes=lambda: (directory / 'z-last').unlink())

    def test_seal_refuses_symlink_and_atomic_publication_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder); (directory / 'target').write_bytes(b'known')
            (directory / 'alias').symlink_to(directory / 'target')
            with self.assertRaises(RuntimeError): seal_files(directory)
            (directory / 'alias').unlink()
            with patch('continuation_lifecycle.os.replace', side_effect=OSError('private operand')):
                with self.assertRaises(OSError): atomic_result(directory, {'accepted': False})
            self.assertFalse((directory / 'result.json').exists())

    def test_fifo_replacement_between_stat_and_open_is_nonblocking_refusal(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder); path = directory / 'race'; path.write_bytes(b'original')
            original_open, changed = os.open, [False]
            def replacing_open(name, flags, *args, **kwargs):
                if Path(name) == path and not changed[0]:
                    self.assertTrue(flags & os.O_NONBLOCK)
                    changed[0] = True; path.unlink(); os.mkfifo(path)
                return original_open(name, flags, *args, **kwargs)
            with patch('continuation_lifecycle.os.open', side_effect=replacing_open):
                with self.assertRaisesRegex(RuntimeError, '^evidence open identity differs$'):
                    seal_files(directory)
            self.assertTrue(changed[0])

    def test_receipt_requires_every_ownership_cleanup_field_and_exact_shape(self):
        lifecycle = ContinuationLifecycle('macos')
        lifecycle.close_admission(); lifecycle.serving_stopped = lifecycle.drained = True
        lifecycle.cleanup['certificate'] = 'completed'
        receipt = lifecycle.receipt(); verify_lifecycle(receipt, 'macos')
        for key, value in [('admission_closed', False), ('active_handlers', 1), ('active_handlers', False),
                ('drained', False), ('serving_stopped', False), ('failed', True), ('cleanup', {}),
                ('outer_limit_seconds', 4801), ('drain_limit_seconds', 91)]:
            with self.assertRaises(RuntimeError): verify_lifecycle(dict(receipt, **{key: value}), 'macos')
        with self.assertRaises(RuntimeError): verify_lifecycle(dict(receipt, extra='private operand'), 'macos')
        with self.assertRaises(RuntimeError): verify_lifecycle({}, 'macos')

    def test_strict_defaults_and_original_strict_source_hashes_preserved(self):
        self.assertIsNone(inspect.signature(fixture).parameters['lifecycle'].default)
        for name, digest in {
            'run.py': '8648f387a4951fb5e779560dc037c48f2018f4e405c9c00193cee4076afc61bb',
            'authenticate.py': 'd1537b9e6c9c80384ce9b6c649d2eaf1873848c4c7ed19be09fdeb13600cd304',
            'contract.py': '3bbc7fca067c77b91ad5d4e3fa96a4e98e1d7ade6bfc5c90dd329b56f7eae3af',
            'ui/PasswordPrivacyUITests.swift': '553ac20541f148098c2e668493359d021a276382e1ed23cf3146191fcb368d56'}.items():
            self.assertEqual(sha(ROOT / 'tests/apple_password_privacy_20261028' / name), digest)
    def test_even_clean_diagnostic_is_never_strict_acceptance(self):
        report = verdict(dict.fromkeys(STAGES, True))
        self.assertTrue(report['strict_privacy_checks_passed'])
        self.assertFalse(report['accepted']); self.assertFalse(report['full_f10_accepted'])
        self.assertTrue(report['diagnostic_only'])

    def test_each_failed_strict_observation_survives_continuation(self):
        for stage in STAGES:
            checks = dict.fromkeys(STAGES, True); checks[stage] = False
            report = verdict(checks)
            self.assertFalse(report['strict_privacy_checks_passed'])
            self.assertEqual(report['failed_strict_checkpoints'], [stage])
            self.assertFalse(report['accepted'])

    def test_incomplete_or_unknown_stages_refuse(self):
        for checks in ({}, dict.fromkeys(STAGES[:-1], True), dict.fromkeys(STAGES + ['foreign'], True)):
            with self.assertRaises(RuntimeError): verdict(checks)

    def test_nonboolean_verdicts_refuse(self):
        for value in (0, 1, 'false', None):
            checks = dict.fromkeys(STAGES, True); checks[STAGES[0]] = value
            with self.assertRaises(RuntimeError): verdict(checks)

    def test_strict_case_cannot_be_replayed_as_diagnostic(self):
        self.assertEqual(case_name(CASE), CASE)
        with self.assertRaises(RuntimeError): case_name('testRememberThenUncheckUpdateDoesNotPersistSessionCredential')


if __name__ == '__main__':
    if os.environ.get('GITHUB_ACTIONS') != 'true': raise RuntimeError('Actions only')
    if len(sys.argv) == 3 and sys.argv[1] == '--timeout-child': timeout_child(Path(sys.argv[2]))
    else: unittest.main()
