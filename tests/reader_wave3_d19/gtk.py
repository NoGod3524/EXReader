"""Prearmed native phase handshake; original cycle driver stays byte-identical."""
import configparser
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import psutil
from reuse import module
from contract import digest, write

original = module('gtk.py')
bus, command = original.bus, original.command

class Driver(original.Driver):
    def __init__(self, out, program, font):
        super().__init__(out, program, font)
        self.stage = 0
        self.epoch = time.monotonic()
        self.timeline = []
        self.old_pid = None
        self.receipt('driver-ready')

    def receipt(self, event, **detail):
        host = self.host.process
        live = host is not None and host.poll() is None
        row = dict(event=event, stage=self.stage, monotonic_seconds=time.monotonic()-self.epoch,
                   unix_seconds=time.time(), controller_pid=os.getpid(), controller_alive=psutil.pid_exists(os.getpid()),
                   host_pid=host.pid if host else None, host_alive=live,
                   exit_code=host.poll() if host else None, detail=detail)
        if live:
            try:
                proc = psutil.Process(host.pid)
                row.update(create_time=proc.create_time(), exe=proc.exe(), threads=[dict(tid=t.id,
                           user_seconds=t.user_time, system_seconds=t.system_time,
                           name=Path('/proc').joinpath(str(host.pid), 'task', str(t.id), 'comm').read_text().strip()) for t in proc.threads()])
            except (psutil.NoSuchProcess, FileNotFoundError):
                row.update(host_alive=host.poll() is None, exit_code=host.poll(), process_transition_during_receipt=True)
        self.timeline.append(row)
        write(self.out / 'pid-phase-timeline.json', self.timeline)
        print('D19_TIMELINE ' + json.dumps(row), flush=True)
        return row

    def catalog(self, label):
        assert self.host.process is not None and self.host.process.poll() == 0, 'SDK readback must not compete with live owner'
        binary = self.out / 'd19-catalog'
        self.receipt('catalog-start', label=label, program_sha256=digest(binary))
        done = subprocess.run([str(binary), str(self.out/'profile')], capture_output=True, text=True, timeout=30)
        (self.out / (label+'-catalog.stdout')).write_text(done.stdout)
        (self.out / (label+'-catalog.stderr')).write_text(done.stderr)
        assert done.returncode == 0, done.stderr
        value = json.loads(done.stdout)
        expected = [self.out/'fixtures'/name for name in ('Reading.txt', 'D14 EPUB.epub', 'Fixed.pdf', 'Comic.cbz', 'Processing.txt', 'search/cancel.epub')]
        assert value['count'] == 6 and sorted(b['sha256'] for b in value['books']) == sorted(digest(p) for p in expected), value
        assert all(b['catalog_matched'] for b in value['books'])
        value.update(label=label, host_pid=self.host.process.pid, host_exit_code=self.host.process.poll(),
                     source_sha=os.environ['GITHUB_SHA'], run=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                     program_sha256=digest(binary), expected_originals={p.relative_to(self.out).as_posix():digest(p) for p in expected})
        write(self.out / (label+'-catalog.json'), value)
        self.receipt('catalog-complete', label=label, sdk_count=value['count'], catalog_count=value['count'], consumer_pid=value['pid'])
        return value

    def launch(self, stage):
        if stage == 2:
            assert self.host.process.poll() == 0
            self.catalog('before-reopen')
            self.old_pid = self.host.process.pid
        self.stage = stage
        self.receipt('launch-request')
        process = super().launch(stage)
        assert stage != 2 or process.pid != self.old_pid
        self.receipt('host-live', state=self.state(), program_sha256=digest(self.host.binary), previous_host_pid=self.old_pid,
                     previous_host_alive=psutil.pid_exists(self.old_pid) if self.old_pid else False)
        return process

    def close_processing(self, path):
        # Keep the old original import and its business outcome. Its short reflow
        # scan is NOT substituted for a proved live scan or retrospectively passed.
        self.open(path, True)
        self.receipt('original-processing-txt-imported', state=self.state(), original_sha256=digest(path))
        self.open(self.out/'fixtures/search/cancel.epub', True)
        assert self.host.read()['bounded'] == 1, 'requires genuine bounded SDK source'
        self.menu('Search within book…')
        self.element('Search within book', {'dialog'})
        self.click('In-book query', {'text'})
        self.host.paste('ABSENT_QUERY_FOR_FULL_CHAPTER_SCAN')
        before = int(self.section('inbook_search')['actions'])
        self.receipt('phase-monitor-armed', expected_action=before+1, state=self.state())
        # Arm BEFORE native input. No Session.key sleep, AT-SPI enumeration or
        # cleanup is allowed between the observed phase and parent close request.
        sender = subprocess.Popen(['xdotool', 'key', '--clearmodifiers', '--delay', '0', 'alt+s'])
        deadline = time.monotonic()+10
        previous = None
        while time.monotonic() < deadline:
            assert self.host.process.poll() is None, 'host exited before phase-2 handshake'
            observed = self.section('inbook_search')
            signature = tuple(observed.get(k) for k in ('actions', 'phase', 'polls', 'running', 'complete'))
            if signature != previous:
                self.receipt('phase-observed', search=observed, native_input_pid=sender.pid)
                previous = signature
            if observed.get('phase') == '2' and int(observed.get('polls', '0')) > 0 and int(observed.get('actions', '0')) == before+1 and observed.get('running') == '1':
                break
            if int(observed.get('actions', '0')) > before and observed.get('phase') == '3':
                raise AssertionError('scan finished before live phase-2 handshake; never convert to success')
            time.sleep(.001)
        else:
            raise TimeoutError('real processing phase not observed: '+repr(self.state()))
        self.receipt('processing-live', search=observed, state=self.host.read())
        close_precondition = self.section('inbook_search')
        assert close_precondition.get('phase') == '2' and close_precondition.get('running') == '1', close_precondition
        request_time = time.monotonic()-self.epoch
        self.receipt('native-close-request', request_seconds=request_time, close_precondition=close_precondition)
        closer = subprocess.Popen(['wmctrl', '-ic', hex(int(self.host.window))])
        self.receipt('native-close-sent', request_seconds=request_time, close_precondition=close_precondition,
                     sender_pid=sender.pid, closer_pid=closer.pid)
        assert sender.wait(timeout=5) == 0 and closer.wait(timeout=5) == 0
        self.host.process.wait(timeout=30)
        self.host.log.close()
        self.receipt('processing-host-exited', search=self.section('inbook_search'))
        assert self.host.process.returncode == 0
        assert self.section('inbook_search').get('visible') == '0', 'close must retire native search'
        shutil.copy2(self.host.observe, self.out/'stage-1-final-state.ini')
        return dict(observed=observed, close_precondition=close_precondition, exit_code=self.host.process.returncode,
                    task='real native search -> phase 2 with control poll -> WM_DELETE parent -> owner exit')

    def no_replay(self):
        value = super().no_replay()
        self.receipt('reopen-no-replay', state=value)
        return value

    def close(self):
        self.receipt('close-requested', state=self.state())
        if self.host.process.poll() is None:
            command('wmctrl', '-ic', hex(int(self.host.window)))
            self.host.process.wait(timeout=20)
        if self.host.log:
            self.host.log.close()
        self.receipt('host-exited')
        assert self.host.process.returncode == 0
        if self.stage == 2:
            self.catalog('after-final-close')
        return dict(exit_code=self.host.process.returncode)
