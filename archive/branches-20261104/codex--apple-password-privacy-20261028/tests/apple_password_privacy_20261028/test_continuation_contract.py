#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import os
import copy
import hashlib
import http.client
import inspect
import json
import plistlib
import re
from pathlib import Path
import socket
import signal
import ssl
import struct
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
from continuation_contract import BUNDLE, ENTITLEMENT_FILE, ENTITLEMENTS, admission_app_identity, admission_tool, entitlement_linker_token, exact_entitlements, macho_entitlement_section, signature_summary, verify_admission_transition, verify_continuation_project
from continuation_contract import BASE, CheckpointTiming, TIMING_PHASES, TIMING_TIMEBASE, validate_checkpoint_timing
from continuation_lifecycle import ContinuationLifecycle, LifecycleHTTPServer, atomic_result, seal_files, verify_lifecycle, write_unsealed
from fixture import fixture
import continuation_log_capture as capture_candidate
from log_evidence import attribute_unified_log as original_attribution
from privacy_scan import needles, scan_file


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


def timing_control(count=4, failed=False):
    source, run, attempt, platform = 'a' * 40, '42', '1', 'macos'
    ticks = iter(range(1000, 2000))
    observer = CheckpointTiming(0, clock=lambda: next(ticks))
    checkpoints = {}
    for index, stage in enumerate(STAGES[:count]):
        scans = {'profile': {'bytes': 10 + index, 'file_count': 1}}
        observer.begin(stage)
        for phase in TIMING_PHASES[:8] if failed else TIMING_PHASES:
            observer.phase(stage, phase)
            if phase == 'first-scan-manifest': observer.counts(stage, scans)
        observer.finish(stage, not failed)
        if not failed:
            checkpoints[stage] = {'profile_id': '00000000-0000-0000-0000-000000000001',
                'archive': stage + '-product.zip', 'archive_sha256': str(index + 1) * 64,
                'network_requests': index * 256, 'strict_privacy_passed': False, 'scans': scans}
    document, summary = observer.snapshot(checkpoints, source, run, attempt, platform)
    return document, summary, checkpoints, (source, run, attempt, platform)


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


def control_macho(section, platform=7, copies=1):
    """Protocol fixture only, not a runnable executable or native proof."""
    command_size = 24 + 72 + 80 * copies
    offset = 32 + command_size
    header = struct.pack('<IiiIIIII', 0xfeedfacf, 0x0100000c, 0, 2, 2, command_size, 0, 0)
    build = struct.pack('<IIIIII', 0x32, 24, platform, 0, 0, 0)
    segment = struct.pack('<II16sQQQQiiII', 0x19, 72 + 80 * copies, b'__TEXT', 0,
                          offset + len(section) * copies, 0, offset + len(section) * copies, 5, 5, copies, 0)
    sections = b''.join(struct.pack('<16s16sQQIIIIIIII', b'__entitlements', b'__TEXT',
        offset + index * len(section), len(section), offset + index * len(section), 0, 0, 0, 0, 0, 0, 0)
        for index in range(copies))
    return header + build + segment + sections + section * copies


def control_project():
    return {'objects': {
        'file': {'isa': 'PBXFileReference', 'path': '/strict/PasswordPrivacyUITests.swift', 'sourceTree': '<group>'},
        'ios': {'isa': 'PBXNativeTarget', 'name': 'EXReaderHost-iOS',
                'productType': 'com.apple.product-type.application', 'buildConfigurationList': 'list'},
        'list': {'isa': 'XCConfigurationList', 'buildConfigurations': ['debug', 'release']},
        'debug': {'isa': 'XCBuildConfiguration', 'name': 'Debug', 'buildSettings': {'OTHER_LDFLAGS': ['$(inherited)', '-lexreader']}},
        'release': {'isa': 'XCBuildConfiguration', 'name': 'Release', 'buildSettings': {'OTHER_LDFLAGS': ['$(inherited)', '-lexreader']}},
        'other': {'isa': 'PBXNativeTarget', 'name': 'EXReaderHost-macOS', 'untouched': True}}}


class ContinuationControls(unittest.TestCase):
    def test_literal_longest_first_closure_and_cross_boundary_overlap_are_required(self):
        values={'user:raw':b'ab','remembered:raw':b'abc','session:raw':b'cde'}
        search=capture_candidate.LiteralRoleSearch(values)
        self.assertEqual(search.roles(b'abcde'),{'user','remembered','session'})
        # These explicit wrong alternatives distinguish the control corpus.
        wrong_order=capture_candidate.LiteralRoleSearch(values); wrong_order.pattern=re.compile(b'ab|abc|cde')
        self.assertNotEqual(wrong_order.roles(b'abcde'),{'user','remembered','session'})
        wrong_closure=capture_candidate.LiteralRoleSearch(values); wrong_closure.closures[b'abc']={'remembered'}
        self.assertNotEqual(wrong_closure.roles(b'abcde'),{'user','remembered','session'})
        nonoverlap=set().union(*(search.closures[match.group(0)] for match in search.pattern.finditer(b'abcde')))
        self.assertNotEqual(nonoverlap,{'user','remembered','session'})
        payload=json.dumps([{'eventMessage':'abcde'}]).encode()
        self.assertEqual(capture_candidate.attribute_unified_log(payload,values),original_attribution(payload,values))

    def test_literal_search_empty_cross_role_binary_and_regex_punctuation(self):
        values={'user:raw':b'', 'remembered:raw':b'a.*(b)[c]\\^$|?\x00',
                'session:raw':b'a.*(b)[c]\\^$|?\x00', 'session:json':b'\x00\nend'}
        for message in ('', 'a.*(b)[c]\\^$|?\x00\nend', 'aZZbcb', 'no match'):
            payload=json.dumps([{'eventMessage':message}]).encode()
            self.assertEqual(capture_candidate.attribute_unified_log(payload,values),original_attribution(payload,values))
        value,state=capture_candidate.attribution_with_state(b'[{"eventMessage":""}]',{'user:raw':b''})
        self.assertFalse(state['candidate_path_used']); self.assertFalse(state['fallback_used'])
        self.assertEqual(state['search_call_count'],0)
        self.assertEqual(value,original_attribution(b'[{"eventMessage":""}]',{'user:raw':b''}))

    def test_literal_search_prefix_heavy_large_messages_keep_full_reference_result(self):
        labels=sorted(capture_candidate.VARIANT_LABELS)[:64]
        values={label:b'a'*(index+1)+b'b' for index,label in enumerate(labels)}
        for message in ('a'*262144+'b', 'a'*262144+'c'):
            payload=json.dumps([{'eventMessage':message}]).encode()
            self.assertEqual(capture_candidate.attribute_unified_log(payload,values),original_attribution(payload,values))

    def test_literal_compiler_fallback_is_explicit_and_cannot_qualify(self):
        payload=b'[{"eventMessage":"needle"}]'; variants={'user:raw':b'needle'}
        class PrivatePatternError(re.error):
            def __str__(self): raise AssertionError('exception text formatted')
        with patch.object(capture_candidate.re,'compile',side_effect=PrivatePatternError('private operand',b'private pattern')):
            value,state=capture_candidate.attribution_with_state(payload,variants)
        self.assertEqual(value,original_attribution(payload,variants))
        self.assertTrue(state['fallback_used']); self.assertFalse(state['candidate_path_used'])
        self.assertFalse(capture_candidate.validate_candidate_state(state,False))
        self.assertNotIn('private',json.dumps(state))

    def test_literal_candidate_preparation_is_inside_each_call_and_eligibility_uninstrumented(self):
        payload=b'[{"eventMessage":"needle"}]'; variants={'user:raw':b'needle'}
        compiler=capture_candidate.re.compile
        with patch.object(capture_candidate.re,'compile',wraps=compiler) as called, \
                patch.object(capture_candidate.time,'monotonic_ns',side_effect=AssertionError('eligibility phase timer used')):
            for unused in range(2):
                value,state=capture_candidate.attribution_with_state(payload,variants)
                self.assertTrue(capture_candidate.validate_candidate_state(state,False))
            self.assertEqual(called.call_count,2)
        self.assertEqual(value,original_attribution(payload,variants))
        self.assertTrue(all(value is None for value in state['phases'].values()))

    def test_literal_subphase_counts_are_finite_and_absent_phases_are_null(self):
        payload=b'[{"eventMessage":"needle"}]'; variants={'user:raw':b'needle'}
        value,state=capture_candidate.attribution_with_state(payload,variants,observe_phases=True)
        self.assertTrue(capture_candidate.validate_candidate_state(state,True))
        self.assertEqual(value,original_attribution(payload,variants))
        self.assertTrue(all(type(value) is int for value in state['phases'].values()))
        unused,invalid=capture_candidate.attribution_with_state(b'not JSON',variants,observe_phases=True)
        self.assertIsNotNone(invalid['phases']['decode_ns'])
        self.assertIsNone(invalid['phases']['prepare_ns']); self.assertIsNone(invalid['phases']['event_loop_ns'])
        self.assertFalse(capture_candidate.validate_candidate_state(invalid,True))
        for bad in (True,-1,1.5,float('nan'),'encoded-private-operand'):
            changed=copy.deepcopy(state); changed['phases']['decode_ns']=bad
            with self.assertRaises(RuntimeError): capture_candidate.validate_candidate_state(changed,True)
        changed=copy.deepcopy(state); changed['phases']['event_loop_ns']=None
        with self.assertRaises(RuntimeError): capture_candidate.validate_candidate_state(changed,True)
        with self.assertRaises(RuntimeError): capture_candidate.validate_candidate_state(state,1)
        with self.assertRaises(RuntimeError): capture_candidate.validate_candidate_state(state,False)

    def test_literal_six_diagnostics_and_twelve_candidate_paths_bind_every_original_sample(self):
        state={'candidate_path_used':True,'fallback_used':False,'literal_event_count':1,'pattern_count':1,'search_call_count':1,
               'phases':dict.fromkeys(('decode_ns','prepare_ns','event_loop_ns','total_ns'))}
        samples=[{'platform':platform,'stage':stage,'files':{name:{'bytes':16,'sha256':'a'*64} for name in capture_candidate.FILES}}
                 for platform in ('macos','iphone') for stage in STAGES[:3]]
        paths=[{'platform':row['platform'],'stage':row['stage'],'order':order,'state':copy.deepcopy(state)}
               for row in samples for order in ('AB','BA')]
        phases=[dict(row,sample_elapsed_ns=20,semantic_parity=True,
                 state=dict(state,phases={'decode_ns':2,'prepare_ns':3,'event_loop_ns':4,'total_ns':10})) for row in samples]
        self.assertTrue(capture_candidate.candidate_evidence_gate(paths,phases,samples))
        fallback=copy.deepcopy(paths); fallback[0]['state'].update(candidate_path_used=False,fallback_used=True,search_call_count=0)
        self.assertFalse(capture_candidate.candidate_evidence_gate(fallback,phases,samples))
        for changed in (phases[:-1],phases+[phases[0]], [dict(row,stage='private-stage') for row in phases]):
            with self.assertRaises(RuntimeError): capture_candidate.candidate_evidence_gate(paths,changed,samples)
        changed=copy.deepcopy(phases); changed[0]['files'][capture_candidate.FILES[0]]['sha256']='b'*64
        with self.assertRaises(RuntimeError): capture_candidate.candidate_evidence_gate(paths,changed,samples)
        changed=copy.deepcopy(phases); changed[0]['state']['search_call_count']=2
        self.assertFalse(capture_candidate.candidate_evidence_gate(paths,changed,samples))
        for changed in (samples[:-1]+[samples[0]], [dict(row,extra='private') for row in samples]):
            with self.assertRaises(RuntimeError): capture_candidate.candidate_evidence_gate(paths,phases,changed)
        changed=copy.deepcopy(samples); changed[0]['files'][capture_candidate.FILES[0]]['bytes']=True
        with self.assertRaises(RuntimeError): capture_candidate.candidate_evidence_gate(paths,phases,changed)

    def test_literal_sender_category_body_remains_frozen_reference(self):
        source=Path(capture_candidate.__file__).read_text()
        start=source.index('        sender = event.get(')
        end=source.index("    report['matched_event_groups']",start)
        self.assertEqual(hashlib.sha256(source[start:end].encode()).hexdigest(),'9f1d0dd1ba6d27a5f809b37ad0eadc0e6f9c54644da7f7f96aa2d0d11b25a952')

    def test_capture_file_sink_keeps_large_complete_stdout_and_stderr(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); lifecycle = ContinuationLifecycle('macos', budget_seconds=20)
            sink = capture_candidate.product_capture(root, STAGES[0])
            script = "import sys; [sys.stdout.buffer.write(b'X'*1048576) for _ in range(65)]; sys.stdout.buffer.write(b'TAIL-CONTROL-ONLY'); sys.stderr.buffer.write(b'COMPLETE-ERROR-CONTROL')"
            done = lifecycle.command([sys.executable, '-c', script], cap=10, max_capture=None, output_sink=sink)
            folder = capture_candidate.publish_product_capture(sink, root, STAGES[0], 'macos', 'a'*40, '1', '1')
            self.assertEqual(done.stdout, folder / 'host-unified.json')
            self.assertEqual(sink.records['host-unified.json']['bytes'], 65*1048576 + len(b'TAIL-CONTROL-ONLY'))
            self.assertEqual((folder / 'capture-stderr.txt').read_bytes(), b'COMPLETE-ERROR-CONTROL')
            self.assertEqual(scan_file(folder / 'host-unified.json', {'user:raw': b'TAIL-CONTROL-ONLY'})['hits'], ['user:raw'])
            self.assertEqual((folder / 'host-unified.json').stat().st_mode & 0o777, 0o600)
            self.assertEqual(folder.stat().st_mode & 0o777, 0o700)

    def test_capture_nonzero_and_timeout_retain_exact_partial_streams_before_raise(self):
        for mode in ('nonzero', 'timeout', 'descendant'):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); lifecycle = ContinuationLifecycle('macos', budget_seconds=4)
                sink = capture_candidate.product_capture(root, STAGES[0])
                script = "import os,sys,time; os.write(1,b'partial-out'); os.write(2,b'partial-error'); "
                script += {'nonzero': 'sys.exit(7)', 'timeout': 'time.sleep(10)',
                    'descendant': 'pid=os.fork(); time.sleep(10) if pid==0 else sys.exit(0)'}[mode]
                with self.assertRaises(RuntimeError):
                    lifecycle.command([sys.executable, '-c', script], cap=0.5, max_capture=None, output_sink=sink)
                self.assertEqual((sink.folder / 'host-unified.json').read_bytes(), b'partial-out')
                self.assertEqual((sink.folder / 'capture-stderr.txt').read_bytes(), b'partial-error')
                self.assertFalse((root / (STAGES[0] + '-product-log-manifest.json')).exists())
                disposition = json.loads((sink.folder.parent / (STAGES[0] + '-capture-disposition.json')).read_text())
                self.assertEqual(disposition['state'], 'failed-capture' if mode == 'nonzero' else 'failed-unsealed')
                self.assertFalse(disposition['valid_capture_manifest'])
                if mode != 'nonzero': self.assertTrue(lifecycle.failed)

    def test_capture_invalid_opt_in_closes_precreated_descriptors_and_retains_refusal(self):
        with tempfile.TemporaryDirectory() as temporary:
            sink=capture_candidate.product_capture(Path(temporary), STAGES[0])
            lifecycle=ContinuationLifecycle('macos', budget_seconds=2)
            with self.assertRaises(RuntimeError): lifecycle.command([sys.executable, '-c', 'pass'], output_sink=sink)
            self.assertEqual(sink.descriptors,{})
            self.assertTrue(lifecycle.failed)
            self.assertIsNone(sink.process)
            self.assertTrue(all((sink.folder/name).read_bytes()==b'' for name in capture_candidate.FILES))
            self.assertEqual(json.loads((sink.folder.parent/(STAGES[0]+'-capture-disposition.json')).read_text())['state'], 'failed-unsealed')

    def test_profile_real_session_deadline_stops_parent_and_preserves_finite_breadcrumbs(self):
        for mode in ('parent-stall','owned-child-stall'):
            with tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary); out=root/'profile'
                summary={'profile_complete':False,'profile_refused':False,'profile_phase':'setup',
                         'native_acceptance':False,'full_f10_accepted':False,'measurements':[]}
                owned=[]; before=signal.getsignal(signal.SIGALRM)
                def body():
                    summary['profile_phase']='sample-binding'
                    if mode=='parent-stall': time.sleep(5)
                    else:
                        sink=capture_candidate.FileCapture(out/'owned'); owned.append(sink)
                        lifecycle=ContinuationLifecycle('macos', budget_seconds=5)
                        lifecycle.command([sys.executable,'-c',"import os,time; os.write(1,b'partial-owned'); time.sleep(5)"],
                                          max_capture=None, output_sink=sink)
                    summary['profile_complete']=True
                    return summary
                result=capture_candidate.bounded_profile_session(out,time.monotonic()+0.25,summary,body)
                self.assertFalse(result['profile_complete']); self.assertFalse(result['performance_gate'])
                self.assertEqual(result['refusal_code'],'deadline-exhausted')
                self.assertEqual(result['profile_phase'],'sample-binding')
                self.assertEqual(json.loads((out/'summary.json').read_text()),result)
                self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))
                self.assertEqual(signal.getsignal(signal.SIGALRM),before)
                if owned:
                    self.assertEqual(owned[0].descriptors,{})
                    self.assertEqual(owned[0].process.wait(timeout=1),-signal.SIGKILL)
                    self.assertFalse(owned[0].terminated)
                    self.assertEqual((owned[0].folder/'host-unified.json').read_bytes(),b'partial-owned')
                    self.assertEqual(json.loads((out/'owned-capture-disposition.json').read_text())['state'],'failed-unsealed')

    def test_capture_refuses_links_fifo_swap_and_late_earlier_stream_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); target = root / 'owned'; target.write_bytes(b'original')
            link = root / 'link'; link.symlink_to(target)
            with self.assertRaises(RuntimeError): capture_candidate.stream_record(link, time.monotonic()+2)
            hard = root / 'hard'; os.link(target, hard)
            with self.assertRaises(RuntimeError): capture_candidate.stream_record(target, time.monotonic()+2)
            hard.unlink()
            original_open = os.open
            def replace_with_fifo(path, flags, *args):
                if Path(path) == target:
                    target.unlink(); os.mkfifo(target)
                return original_open(path, flags, *args)
            with patch.object(capture_candidate.os, 'open', side_effect=replace_with_fifo):
                with self.assertRaises(RuntimeError): capture_candidate.stream_record(target, time.monotonic()+2)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); sink = capture_candidate.product_capture(root, STAGES[0])
            lifecycle = ContinuationLifecycle('macos', budget_seconds=4)
            original_record = capture_candidate.stream_record
            def mutate_earlier(path, deadline, descriptor=None):
                result = original_record(path, deadline, descriptor)
                if Path(path).name == 'capture-stderr.txt': (sink.folder / 'host-unified.json').write_bytes(b'late-change')
                return result
            with patch.object(capture_candidate, 'stream_record', side_effect=mutate_earlier):
                with self.assertRaises(RuntimeError):
                    lifecycle.command([sys.executable, '-c', "import os; os.write(1,b'original'); os.write(2,b'err')"],
                                      max_capture=None, output_sink=sink)
            self.assertTrue(lifecycle.failed); self.assertIsNone(sink.records)

    def test_capture_refuses_manifest_after_swap_and_deadline_never_clean(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); sink = capture_candidate.product_capture(root, STAGES[0])
            lifecycle = ContinuationLifecycle('macos', budget_seconds=4)
            lifecycle.command([sys.executable, '-c', "import os; os.write(1,b'original')"], max_capture=None, output_sink=sink)
            (sink.folder / 'host-unified.json').write_bytes(b'changed')
            with self.assertRaises(RuntimeError): capture_candidate.publish_product_capture(sink, root, STAGES[0], 'macos', 'a'*40, '1', '1')
            with self.assertRaises(RuntimeError): capture_candidate.read_payload(sink.folder / 'host-unified.json', time.monotonic()-1)
            self.assertFalse((root / (STAGES[0] + '-product-log-manifest.json')).exists())

    def test_capture_candidate_attribution_exact_all_roles_encodings_and_overlaps(self):
        values = {role: ('control-' + role + '-value-0123456789').encode() for role in
            ('user', 'remembered', 'session', 'remembered-pair', 'session-pair', 'remembered-authorization', 'session-authorization')}
        variants = needles(values)
        for value in variants.values():
            # Include all byte forms representable as eventMessage UTF8; byte
            # scanning remains authoritative for undecodable raw encodings.
            try: message = value.decode('utf8')
            except UnicodeDecodeError: continue
            payload = json.dumps([{'eventMessage': message, 'senderImagePath': '/System/Library/Frameworks/AppKit.framework/AppKit'}]).encode()
            self.assertEqual(capture_candidate.attribute_unified_log(payload, variants), original_attribution(payload, variants))
        variants = {'user:raw': b'', 'remembered:raw': b'ab', 'session:raw': b'ab', 'session:hex': b'abc', 'remembered:json': b'b'}
        payload = b'[{"eventMessage":"abcab"},{"eventMessage":""}]'
        self.assertEqual(capture_candidate.attribute_unified_log(payload, variants), original_attribution(payload, variants))
        self.assertEqual(capture_candidate.attribute_unified_log(payload, variants)['matched_event_groups'][1]['credential_roles'], ['user'])

    def test_capture_matcher_preserves_json_decoding_and_original_exceptions(self):
        variants = {'user:raw': b'needle'}
        text = '[{"eventMessage":"old","eventMessage":"needle"},null,42,{"eventMessage":false}]'
        payloads = [text.encode(encoding) for encoding in ('utf8', 'utf16', 'utf32')]
        payloads += [b'[] trailing', b'{"not":"array"}', b'\xff', b'[{"eventMessage":"\\ud800"}]', b'[]']
        for payload in payloads:
            self.assertEqual(capture_candidate.profile_outcome(capture_candidate.attribute_unified_log, payload, variants),
                             capture_candidate.profile_outcome(original_attribution, payload, variants))
        bad = {'user:raw': []}
        for payload in (b'[]', b'[{"eventMessage":"needle"}]'):
            self.assertEqual(capture_candidate.profile_outcome(capture_candidate.attribute_unified_log, payload, bad),
                             capture_candidate.profile_outcome(original_attribution, payload, bad))

    def test_profile_oracle_identity_and_shape_refuse_before_needles(self):
        oracle = {'synthetic_only': True, 'source_sha': 'a'*40, 'run_id': '1', 'attempt': '1',
                  'user': 'privacy-user-'+'a'*32, 'passwords': {'remembered': 'Privacy-'+'a'*64+'!%:+', 'session': 'Privacy-'+'b'*64+'!%:+'}}
        self.assertTrue(capture_candidate.oracle_variants(oracle, 'a'*40, '1', '1'))
        for change in ({'synthetic_only': False}, {'source_sha': 'b'*40}, {'user': 'private-value'},
                       {'passwords': dict.fromkeys(('remembered', 'session'), 'Privacy-'+'a'*64+'!%:+')}, {'extra': 'private-value'}):
            with self.assertRaises(RuntimeError): capture_candidate.oracle_variants(dict(oracle, **change), 'a'*40, '1', '1')

    def test_profile_full_cartesian_measurements_and_performance_gate(self):
        rows = [dict(platform=platform, stage=stage, comparison=comparison, order=order, implementation=implementation,
                     elapsed_ns=100 if implementation == 'reference' else 70, parity=True)
                for platform in ('macos','iphone') for stage in STAGES[:3] for comparison in ('capture','attribution')
                for order in ('AB','BA') for implementation in ('reference','candidate')]
        self.assertTrue(capture_candidate.profile_gate(rows)['performance_gate'])
        for changed in (rows[:-1], rows+[rows[0]], [dict(row, elapsed_ns=True) for row in rows],
                        [dict(row, stage='private-operand') for row in rows], [dict(row, parity=False) for row in rows]):
            with self.assertRaises(RuntimeError): capture_candidate.profile_gate(changed)
        slow = [dict(row, elapsed_ns=105 if row['implementation']=='candidate' else 100) for row in rows]
        self.assertFalse(capture_candidate.profile_gate(slow)['performance_gate'])
        one_order = [dict(row, elapsed_ns=95 if row['order']=='BA' and row['implementation']=='candidate' else row['elapsed_ns']) for row in rows]
        gate=capture_candidate.profile_gate(one_order)
        self.assertFalse(gate['both_order_aggregate_20_percent_improvement'])
        self.assertTrue(gate['no_sample_mean_regression_over_10_percent']); self.assertFalse(gate['performance_gate'])
        one_sample = [dict(row, elapsed_ns=115 if row['platform']=='iphone' and row['stage']==STAGES[0] and row['implementation']=='candidate' else row['elapsed_ns']) for row in rows]
        gate=capture_candidate.profile_gate(one_sample)
        self.assertTrue(gate['both_order_aggregate_20_percent_improvement'])
        self.assertFalse(gate['no_sample_mean_regression_over_10_percent']); self.assertFalse(gate['performance_gate'])
        self.assertFalse(capture_candidate.profile_gate(rows)['native_authorized'])

    def test_profile_mode_is_exact_and_never_coexists_with_native_or_diagnostics(self):
        self.assertTrue(capture_candidate.profile_marker_valid('owned '+capture_candidate.PROFILE_MARKER))
        for value in ('', capture_candidate.PROFILE_MARKER*2, None, True):
            self.assertFalse(capture_candidate.profile_marker_valid(value))
        for marker in capture_candidate.OTHER_MARKERS:
            self.assertFalse(capture_candidate.profile_marker_valid(capture_candidate.PROFILE_MARKER+marker))

    def test_capture_original_default_reconstructs_historical_source_and_imports(self):
        package = ROOT / 'tests/apple_password_privacy_20261028'
        source = (package / 'continuation_lifecycle.py').read_text()
        source = source.replace(', output_sink=None):', '):')
        source = source.replace('        if output_sink is not None:\n            return output_sink.command(self, argv, cap, check, cwd, env, max_capture)\n', '')
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(), capture_candidate.REFERENCE_HASHES['continuation_lifecycle.py'])
        for name, digest in capture_candidate.REFERENCE_HASHES.items():
            if name != 'continuation_lifecycle.py': self.assertEqual(sha(package / name), digest)
        self.assertEqual(sha(package / 'authenticate_continuation.py'), '4e0127c553d22a765cfcbf9274aa6f476b55afaed5f25f6eda22ded5209ac54b')

    def test_profile_actual_worker_protocol_against_pinned_historical_source(self):
        # Actions-only protocol fixture, not a real retained/native sample.
        from log_evidence import retain_product_log
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); reference = root / 'reference'; reference.mkdir(mode=0o700)
            for name, expected in capture_candidate.REFERENCE_HASHES.items():
                data = subprocess.check_output(['git', 'show', capture_candidate.SOURCE+':tests/apple_password_privacy_20261028/'+name], cwd=ROOT)
                self.assertEqual(hashlib.sha256(data).hexdigest(), expected)
                (reference / name).write_bytes(data)
            oracle = {'synthetic_only': True, 'source_sha': capture_candidate.SOURCE, 'run_id': capture_candidate.RUN, 'attempt': '1',
                'user': 'privacy-user-'+'a'*32, 'passwords': {'remembered': 'Privacy-'+'a'*64+'!%:+', 'session': 'Privacy-'+'b'*64+'!%:+'}}
            oracle_path = root / 'oracle.json'; capture_candidate.write_private_json(oracle_path, oracle)
            variants = capture_candidate.oracle_variants(oracle, capture_candidate.SOURCE, capture_candidate.RUN, '1')
            payload = json.dumps([{'eventMessage': oracle['user'], 'senderImagePath':'/System/Library/XCTest.framework/XCTest'}]).encode()
            raw = root / 'raw'; raw.mkdir(mode=0o700)
            folder = retain_product_log(raw, STAGES[0], 'macos', capture_candidate.SOURCE, capture_candidate.RUN, '1', payload, b'', 0)
            manifest = json.loads((raw / (STAGES[0]+'-product-log-manifest.json')).read_text())
            spec = {'platform': 'macos', 'stage': STAGES[0], 'oracle': str(oracle_path), 'manifest': manifest,
                'streams': {name:str(folder/name) for name in capture_candidate.FILES},
                'scans': {name:scan_file(folder/name, variants) for name in capture_candidate.FILES},
                'attribution': original_attribution(payload, variants)}
            spec_path = root/'spec.json'; capture_candidate.write_private_json(spec_path, spec)
            for mode in ('capture-reference','capture-candidate','attribution-reference','attribution-candidate','phases-candidate'):
                output=root/mode; output.mkdir(mode=0o700)
                done=subprocess.run([sys.executable, '-B', str(Path(capture_candidate.__file__)), '--worker', mode,
                    str(spec_path), str(output), str(reference), str(time.monotonic()+20)], capture_output=True, timeout=25)
                self.assertEqual(done.returncode,0); self.assertEqual(done.stdout,b''); self.assertEqual(done.stderr,b'')
                measurement=json.loads((output/'measurement.json').read_text())
                self.assertTrue(measurement['parity']); self.assertGreater(measurement['elapsed_ns'],0)
                if mode in ('attribution-candidate','phases-candidate'):
                    self.assertTrue(capture_candidate.validate_candidate_state(measurement['candidate_state'],mode=='phases-candidate'))
            (reference/'continuation_lifecycle.py').write_text('private-operand')
            with self.assertRaises(RuntimeError): capture_candidate.reference_modules(reference,time.monotonic()+2)

    def test_timing_four_original_checkpoints_have_exact_order_and_identity(self):
        document, summary, checkpoints, identity = timing_control()
        self.assertTrue(summary['valid']); self.assertTrue(summary['observed'])
        self.assertEqual([row['stage'] for row in summary['records']], STAGES)
        self.assertEqual(summary['records'][0]['entered_ms'], 1000000)
        self.assertEqual(summary['records'][0]['phases'][0]['began_ms'], 1001000)
        self.assertEqual(len({row['checkpoint_identity'] for row in summary['records']}), 4)
        self.assertTrue(all(row['scan_counts']['profile']['file_count'] == 1 for row in summary['records']))
        self.assertEqual(summary, validate_checkpoint_timing(document, checkpoints, *identity))
        for key in ('external_clock_verified', 'http_response_delivery_proven', 'native_acceptance', 'full_f10_accepted'):
            self.assertFalse(summary[key])

    def test_timing_partial_failed_phase_and_missing_is_not_zero(self):
        document, summary, checkpoints, identity = timing_control(count=1, failed=True)
        row = summary['records'][0]
        self.assertEqual(row['state'], 'failed'); self.assertEqual(row['phases'][-1]['state'], 'failed')
        self.assertEqual(row['phases'][-1]['phase'], 'second-scan'); self.assertIsNone(row['checkpoint_identity'])
        self.assertEqual(len(row['phases']), 8); self.assertEqual(checkpoints, {})
        empty, proof = CheckpointTiming(0, lambda: 1).snapshot({}, *identity)
        self.assertTrue(proof['valid']); self.assertFalse(proof['observed']); self.assertEqual(proof['records'], [])
        self.assertNotEqual(proof, summary)
        observer = CheckpointTiming(0, lambda: 1); observer.begin(STAGES[0])
        with self.assertRaisesRegex(RuntimeError, '^timing finalized callback remains open$'):
            observer.snapshot({}, *identity)
        changed = copy.deepcopy(document); changed['records'][0]['state'] = 'completed'
        with self.assertRaises(RuntimeError): validate_checkpoint_timing(changed, checkpoints, *identity)

    def test_timing_rejects_boolean_nonfinite_out_of_horizon_and_global_regression(self):
        document, unused, checkpoints, identity = timing_control()
        for bad in (True, False, -1, 4800001, 1.5, float('nan'), float('inf'), 'encoded-private-operand'):
            changed = copy.deepcopy(document); changed['records'][0]['entered_ms'] = bad
            with self.assertRaises(RuntimeError): validate_checkpoint_timing(changed, checkpoints, *identity)
        for callback, phase, field, value in [(0, 0, 'began_ms', 999), (0, 1, 'ended_ms', 1000), (1, None, 'entered_ms', 1001)]:
            changed = copy.deepcopy(document)
            row = changed['records'][callback]
            (row if phase is None else row['phases'][phase])[field] = value
            with self.assertRaises(RuntimeError): validate_checkpoint_timing(changed, checkpoints, *identity)

    def test_timing_rejects_duplicate_foreign_records_phases_roots_and_binding(self):
        document, unused, checkpoints, identity = timing_control()
        changes = []
        value = copy.deepcopy(document); value['records'].append(copy.deepcopy(value['records'][-1])); changes.append(value)
        value = copy.deepcopy(document); value['records'][1]['stage'] = STAGES[0]; changes.append(value)
        value = copy.deepcopy(document); value['records'][0]['stage'] = 'private-operand'; changes.append(value)
        value = copy.deepcopy(document); value['records'][0]['phases'][1]['phase'] = TIMING_PHASES[0]; changes.append(value)
        value = copy.deepcopy(document); value['records'][0]['checkpoint_identity'] = value['records'][1]['checkpoint_identity']; changes.append(value)
        value = copy.deepcopy(document); value['records'][0]['scan_counts'] = {'private-operand': {'bytes': 1, 'file_count': 1}}; changes.append(value)
        value = copy.deepcopy(document); value['records'][0]['scan_counts']['profile']['bytes'] = True; changes.append(value)
        value = copy.deepcopy(document); value['records'][0]['scan_counts'] = {}; changes.append(value)
        value = copy.deepcopy(document); value['records'][0]['phases'][-1]['state'] = 'open'; changes.append(value)
        value = copy.deepcopy(document); value['timebase'] = 'wall-clock'; changes.append(value)
        for changed in changes:
            with self.assertRaises(RuntimeError): validate_checkpoint_timing(changed, checkpoints, *identity)
        for stages in ([STAGES[0], STAGES[0]], ['private-operand']):
            observer = CheckpointTiming(0, lambda: 1)
            for stage in stages: observer.begin(stage)
            with self.assertRaises(RuntimeError): observer.snapshot({}, *identity)

    def test_timing_observer_failure_never_replaces_original_callback_error(self):
        class OriginalFailure(Exception): pass
        def broken_clock(): raise ValueError('private clock operand')
        observer = CheckpointTiming(0, broken_clock)
        with self.assertRaises(OriginalFailure):
            observer.begin(STAGES[0])
            try:
                observer.phase(STAGES[0], TIMING_PHASES[0])
                observer.counts(STAGES[0], {'private-operand': {}})
                raise OriginalFailure()
            finally: observer.finish(STAGES[0], False)
        with self.assertRaisesRegex(RuntimeError, '^timing observer unavailable$'):
            observer.snapshot({}, 'a' * 40, '42', '1', 'macos')

    def test_timing_independent_replay_binds_all_members_summary_and_original_scan(self):
        from authenticate_continuation import replay_checkpoint_timing
        document, summary, checkpoints, identity = timing_control(count=1)
        lifecycle = ContinuationLifecycle('macos'); lifecycle.admission_open = False
        lifecycle.serving_stopped = lifecycle.drained = True; lifecycle.cleanup['certificate'] = 'completed'
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def write_evidence():
                (root / 'result.json').unlink(missing_ok=True)
                (root / 'checkpoint-timing.json').write_text(json.dumps(document))
                (root / 'checkpoints.json').write_text(json.dumps(checkpoints))
                (root / (STAGES[0] + '-privacy-scan.json')).write_text(json.dumps(checkpoints[STAGES[0]]['scans']))
                result = {'source_sha': identity[0], 'run_id': identity[1], 'attempt': identity[2], 'platform': identity[3],
                    'base_sha': BASE, 'accepted': False, 'diagnostic_only': True, 'full_f10_accepted': False,
                    'evidence_sealed': True, 'lifecycle': lifecycle.receipt(), 'checkpoints': checkpoints,
                    'checkpoint_timing': summary, 'files': seal_files(root)}
                (root / 'result.json').write_text(json.dumps(result))
                return result
            result = write_evidence()
            proof = replay_checkpoint_timing(root, *identity)
            self.assertTrue(proof['original_member_replay']); self.assertFalse(proof['signature_replay_credited'])
            (root / 'checkpoint-timing.json').write_text('{}')
            with self.assertRaises(RuntimeError): replay_checkpoint_timing(root, *identity)
            result = write_evidence(); result['checkpoint_timing']['observed'] = False
            (root / 'result.json').write_text(json.dumps(result))
            with self.assertRaises(RuntimeError): replay_checkpoint_timing(root, *identity)
            summary['observed'] = True; write_evidence()
            (root / (STAGES[0] + '-privacy-scan.json')).write_text(json.dumps({'profile': {'bytes': 999, 'file_count': 1}}))
            (root / 'result.json').unlink(); result['checkpoint_timing'] = summary; result['files'] = seal_files(root)
            (root / 'result.json').write_text(json.dumps(result))
            with self.assertRaises(RuntimeError): replay_checkpoint_timing(root, *identity)
            # Even a structurally coherent open record cannot be certified
            # after the receipt proves every callback handler has ended.
            document['records'][0].update(state='open', exited_ms=None)
            document['records'][0]['phases'][-1].update(state='open', ended_ms=None)
            summary = validate_checkpoint_timing(document, checkpoints, *identity)
            write_evidence()
            with self.assertRaisesRegex(RuntimeError, '^timing finalized callback remains open$'):
                replay_checkpoint_timing(root, *identity)

    def test_timing_aggregate_never_turns_failed_native_or_failed_controls_into_acceptance(self):
        import authenticate_continuation as auth
        source, run, attempt = 'a' * 40, '42', '1'
        names = ['Privacy oracle rejection controls', 'Privacy SDK macos', 'Privacy SDK iphonesimulator'] + [
            'Privacy diagnostic continuation ' + platform for platform in ('macos', 'iphone', 'ipad')]
        archive = b'controlled-download-bytes'
        artifacts = [{'id': index + 1, 'name': 'password-continuation-native-' + platform + '-42-1',
            'expired': False, 'workflow_run': {'head_sha': source, 'id': 42},
            'size_in_bytes': len(archive), 'digest': 'sha256:' + hashlib.sha256(archive).hexdigest()}
            for index, platform in enumerate(('macos', 'iphone', 'ipad'))]
        for mode in ('native-failed', 'full-validator-refused', 'controls-failed', 'sdk-failed'):
            jobs = [{'name': name, 'head_sha': source, 'status': 'completed', 'conclusion': 'success'} for name in names]
            if mode == 'native-failed': jobs[4]['conclusion'] = 'failure'
            if mode == 'controls-failed': jobs[0]['conclusion'] = 'failure'
            if mode == 'sdk-failed': jobs[1]['conclusion'] = 'failure'
            def api(argv):
                if '/jobs?' in argv[-1]: return json.dumps({'jobs': jobs}).encode()
                if '/artifacts?' in argv[-1]: return json.dumps({'artifacts': artifacts}).encode()
                raise AssertionError('unexpected control API')
            def download(argv, **kwargs):
                kwargs['stdout'].write(archive)
                return subprocess.CompletedProcess(argv, 0)
            def full_validate(directory, supplied_source, supplied_run, supplied_attempt, platform):
                if mode == 'full-validator-refused' and platform == 'iphone': raise RuntimeError('private refusal operand')
                return {'accepted': False, 'full_f10_accepted': False}
            with tempfile.TemporaryDirectory() as temporary, patch.object(auth, 'ROOT', Path(temporary)), \
                    patch.object(auth, 'guard'), patch.object(auth.sys, 'platform', 'darwin'), \
                    patch.dict(os.environ, {'GITHUB_ACTIONS': 'true', 'GITHUB_SHA': source, 'GITHUB_RUN_ID': run,
                        'GITHUB_RUN_ATTEMPT': attempt, 'GITHUB_REPOSITORY': 'fixture/owned'}), \
                    patch.object(auth.subprocess, 'check_output', side_effect=api), \
                    patch.object(auth.subprocess, 'run', side_effect=download) as downloaded, \
                    patch.object(auth, 'safe_extract'), patch.object(auth, 'replay_checkpoint_timing',
                        side_effect=lambda *args: {'valid': True, 'native_acceptance': False, 'full_f10_accepted': False}) as replay, \
                    patch.object(auth, 'validate', side_effect=full_validate) as full, patch('builtins.print'):
                with self.assertRaises(RuntimeError): auth.main()
                summary = json.loads((Path(temporary) / 'build/apple-password-continuation-summary/summary.json').read_text())
                self.assertFalse(summary['probe_integrity_verified']); self.assertFalse(summary['accepted'])
                self.assertFalse(summary['full_f10_accepted'])
                self.assertNotIn('private refusal operand', json.dumps(summary))
                if mode in ('controls-failed', 'sdk-failed'):
                    replay.assert_not_called(); full.assert_not_called(); downloaded.assert_not_called()
                else:
                    self.assertEqual(set(summary['timing_replays']), {'macos', 'iphone', 'ipad'})
                    self.assertEqual(summary['timing_replay_failures'], {})
                    if mode == 'native-failed':
                        full.assert_not_called(); self.assertEqual(summary['continuation_replay_failures'], {})
                    else:
                        self.assertEqual(full.call_count, 3)
                        self.assertEqual(summary['continuation_replay_failures'], {'iphone': 'unavailable-or-invalid'})
    def test_timing_wrappers_reconstruct_original_checkpoint_and_full_validator(self):
        runner = (ROOT / 'tests/apple_password_privacy_20261028/continuation_run.py').read_text()
        body = runner[runner.index('        def checkpoint(stage, requests):'):runner.index('        def timed_checkpoint(stage, requests):')]
        body = '\n'.join(line for line in body.splitlines() if not re.fullmatch(
            r"            timing\.(?:phase\(stage, '[a-z-]+'\)|counts\(stage, scans\))", line)).rstrip() + '\n'
        body = body.replace('            capture = product_capture(evidence, stage)\n', '')
        body = body.replace(', output_sink=capture)', ')')
        body = body.replace("            log_root = publish_product_capture(capture, evidence, stage, platform, result['source_sha'], result['run_id'], result['attempt'])\n",
            "            log_root = retain_product_log(evidence, stage, platform, result['source_sha'], result['run_id'],\n                                          result['attempt'], done.stdout, done.stderr, done.returncode)\n")
        body = body.replace("require(capture.nonblank, 'actual product log capture was empty')", "require(bool(done.stdout.strip()), 'actual product log capture was empty')")
        body = body.replace("attribute_unified_log(read_payload(done.stdout, lifecycle.deadline, capture.records['host-unified.json']), variants, deadline=lifecycle.deadline)", 'attribute_unified_log(done.stdout, variants)')
        self.assertEqual(hashlib.sha256(body.encode()).hexdigest(), 'f9acb36b1c9209017c857b8ebb397a767c2ecc8a0f90262df4c379e0e97665a1')
        self.assertEqual(runner.count('timing.phase(stage,'), len(TIMING_PHASES))
        auth = (ROOT / 'tests/apple_password_privacy_20261028/authenticate_continuation.py').read_text()
        body = auth[auth.index('def validate(directory, source, run, attempt, platform):'):auth.index('\ndef replay_checkpoint_timing(')]
        body = body.replace('    timing = replay_checkpoint_timing(directory, source, run, attempt, platform)\n', '')
        body = body.replace('                checkpoint_timing=timing,\n', '').rstrip() + '\n'
        self.assertEqual(hashlib.sha256(body.encode()).hexdigest(), 'f658ac04578abfd98d57627058ec1bc8078b37a99605a1a03aaada727a10f868')
        self.assertIn("all(job['head_sha'] == source and job['status'] == 'completed' and job['conclusion'] == 'success' for job in producers)", auth)
        workflow = (ROOT / '.github/workflows/apple-password-privacy-20261028.yml').read_text()
        self.assertIn('    timeout-minutes: 20\n', workflow)
        self.assertEqual(workflow.count('--capture-profile'), 1)
        self.assertIn('          path: build/apple-password-capture-profile/summary.json\n', workflow)
        self.assertNotIn('workflow_dispatch', workflow)
        profile = workflow[workflow.index('  capture-profile:\n'):workflow.index('  prior-diagnostic:\n')]
        self.assertIn('    needs: contract\n', profile)
        self.assertNotIn('private-work', profile)
        workflow = workflow.replace(profile, '')
        workflow = workflow.replace('      - name: Reject mixed capture profile modes\n        run: python3 -B tests/apple_password_privacy_20261028/continuation_log_capture.py --check-mode\n', '')
        old_if = "contains(github.event.head_commit.message, '[privacy-diagnostic]') || contains(github.event.head_commit.message, '[privacy-native-diagnostic]') || contains(github.event.head_commit.message, '[privacy-continuation-diagnostic]')"
        workflow = workflow.replace('"!contains(github.event.head_commit.message, \'[privacy-capture-profile]\') && ('+old_if+')"', old_if)
        workflow = workflow.replace(" && !contains(github.event.head_commit.message, '[privacy-capture-profile]')", '')
        self.assertEqual(hashlib.sha256(workflow.encode()).hexdigest(), '3eb24789a79b48d2a0af24c7b7c9cf2ed526afc3403e5c7e986840cd35adb673')

    def test_entitlements_are_exact_and_reject_duplicate_foreign_or_nonboolean(self):
        source = ENTITLEMENT_FILE.read_bytes()
        self.assertEqual(exact_entitlements(source), ENTITLEMENTS)
        for data in [source.replace(b'<true/>', b'<integer>1</integer>'),
                source.replace(BUNDLE.encode(), b'foreign.group', 1),
                source.replace(b'</array>', b'<string>*</string></array>'),
                source.replace(b'</dict>', b'<key>get-task-allow</key><true/></dict>'),
                source.replace(b'<true/>', b'<false/>'), b'', b'\x00' + source,
                plistlib.dumps(ENTITLEMENTS, fmt=plistlib.FMT_BINARY)]:
            with self.assertRaises(RuntimeError):
                exact_entitlements(data)

    def test_macho_section_requires_exact_simulator_bounds_and_unique_section(self):
        source = ENTITLEMENT_FILE.read_bytes(); data = control_macho(source)
        proof = macho_entitlement_section(data)
        self.assertEqual(proof['section_sha256'], hashlib.sha256(source).hexdigest())
        self.assertEqual(proof['platform'], 'ios-simulator')
        bad_offset = bytearray(data); struct.pack_into('<I', bad_offset, 32 + 24 + 72 + 48, 0)
        bad_size = bytearray(data); struct.pack_into('<I', bad_size, 32 + 24 + 4, 8)
        for altered in [data[:31], data[:-1], b'\xca\xfe\xba\xbe' + data[4:],
                control_macho(source, platform=2), control_macho(source, copies=0),
                control_macho(source, copies=2), bytes(bad_offset), bytes(bad_size),
                control_macho(source.replace(BUNDLE.encode(), b'foreign.group', 1))]:
            with self.assertRaises(RuntimeError): macho_entitlement_section(altered)

    def test_exact_project_delta_cannot_admit_other_targets_flags_or_settings(self):
        before = control_project(); after = copy.deepcopy(before)
        probe, entitlement = Path('/owned/Continuation.swift'), Path('/owned/path with spaces/ios.entitlements')
        after['objects']['file'].update(path=str(probe), sourceTree='<absolute>')
        mac = copy.deepcopy(after)
        verify_continuation_project(before, mac, probe, entitlement, 'macos')
        for key in ('debug', 'release'):
            after['objects'][key]['buildSettings']['OTHER_LDFLAGS'].append(entitlement_linker_token(entitlement))
        verify_continuation_project(before, after, probe, entitlement, 'iphone')
        for target, key, value in [('other', 'untouched', False), ('file', 'path', '/foreign.swift'),
                ('debug', 'buildSettings', {'OTHER_LDFLAGS': ['-lforeign']}),
                ('release', 'timeout', 4801), ('ios', 'name', 'Foreign')]:
            altered = copy.deepcopy(after); altered['objects'][target][key] = value
            with self.assertRaises(RuntimeError): verify_continuation_project(before, altered, probe, entitlement, 'iphone')
        with self.assertRaises(RuntimeError): verify_continuation_project(before, after, probe, entitlement, 'macos')
        for value in ('relative/path', '/foreign,path', '/bad\npath'):
            with self.assertRaises(RuntimeError): entitlement_linker_token(value)
        self.assertEqual(before, control_project())

    def test_signature_zero_exit_is_not_identity_or_entitlement_proof(self):
        display = ('Identifier=' + BUNDLE + '\nSignature=adhoc\nTeamIdentifier=not set\n').encode()
        self.assertTrue(signature_summary(display, 0)['verified'])
        self.assertFalse(signature_summary(b'', 1, require_valid=False)['verified'])
        for text, code in [(b'', 0), (display, 1), (display + b'Signature=adhoc\n', 0),
                (display.replace(BUNDLE.encode(), b'foreign.group'), 0),
                (display.replace(b'adhoc', b'adhoc%3Aprivate'), 0),
                (display.replace(b'not set', b'private...'), 0)]:
            with self.assertRaises(RuntimeError): signature_summary(text, code)

    def test_admission_app_identity_and_installed_byte_binding_refuse_substitution(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Path(folder); (app / 'Frameworks').mkdir()
            (app / 'EXReaderHost').write_bytes(control_macho(ENTITLEMENT_FILE.read_bytes()))
            (app / 'Frameworks/libexreader.3.42.0.dylib').write_bytes(b'unchanged protocol fixture SDK')
            info = {'CFBundleIdentifier': BUNDLE, 'CFBundleExecutable': 'EXReaderHost', 'EXRSourceSHA': 'a' * 40,
                    'EXRSDKVersion': '3.42.0', 'EXRPageThemeEnabled': True}
            (app / 'Info.plist').write_bytes(plistlib.dumps(info))
            before = admission_app_identity(app, 'a' * 40, seal_files(app))
            before['signature'] = {'verified': False}
            after = copy.deepcopy(before); after['signature'] = {'verified': True}
            after['binary'] = {'bytes': 100, 'sha256': 'b' * 64}
            after['files']['EXReaderHost'] = after['binary']
            after['files']['_CodeSignature/CodeResources'] = {'bytes': 10, 'sha256': 'c' * 64}
            installed = copy.deepcopy(after)
            self.assertTrue(verify_admission_transition(before, after, installed)['built_and_installed_verified'])
            for key in ('info', 'section', 'libraries', 'binary', 'signature'):
                altered = copy.deepcopy(installed); altered[key] = {'verified': False} if key == 'signature' else {}
                with self.assertRaises(RuntimeError): verify_admission_transition(before, after, altered)
            altered = copy.deepcopy(installed); altered['files']['new-resource'] = {'bytes': 1, 'sha256': 'd' * 64}
            with self.assertRaises(RuntimeError): verify_admission_transition(before, after, altered)
            changed_after = copy.deepcopy(altered)
            with self.assertRaises(RuntimeError): verify_admission_transition(before, changed_after, altered)
            for key, value in [('CFBundleIdentifier', 'foreign.group'), ('CFBundleExecutable', 'Other'),
                    ('EXRSourceSHA', 'c' * 40), ('EXRSDKVersion', '0'), ('EXRPageThemeEnabled', False)]:
                (app / 'Info.plist').write_bytes(plistlib.dumps(dict(info, **{key: value})))
                with self.assertRaises(RuntimeError): admission_app_identity(app, 'a' * 40, seal_files(app))

    def test_admission_inspection_uses_shared_deadline_and_retains_failed_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); commands = []
            lifecycle = ContinuationLifecycle('iphone', budget_seconds=2, drain_seconds=0.1)
            done = admission_tool(lifecycle, root, 'installed-display', [sys.executable, '-c',
                'import sys,time; print("fixed-control",flush=True); time.sleep(60)'], commands)
            self.assertNotEqual(done.returncode, 0); self.assertTrue(lifecycle.failed)
            self.assertEqual((root / 'ios-admission/installed-display.stdout').read_bytes(), b'fixed-control\n')
            self.assertEqual(commands, [{'role': 'admission-installed-display', 'exit': done.returncode}])
            with self.assertRaises(RuntimeError):
                admission_tool(lifecycle, root, 'installed-verify', [sys.executable, '-c', 'raise SystemExit(0)'], commands)
            self.assertFalse((root / 'ios-admission/installed-verify.stdout').exists())
            write_unsealed(root, 'a' * 40, 'iphone', lifecycle)
            self.assertFalse((root / 'result.json').exists())
            self.assertFalse(json.loads((root / 'unsealed.json').read_text())['evidence_sealed'])

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
