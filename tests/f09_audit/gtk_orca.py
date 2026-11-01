"""F09 GTK screen reader: what Orca actually speaks on the compact host.

AT-SPI results (gtk_compact.py) say what an assistive client can read; they
are not a screen-reader result. This lane runs a real Orca with its debug log
inside the same accessibility session, drives the same compact flow with real
keys, then reads Orca's own SPEECH OUTPUT lines. Human listening is a separate
record that this lane does not claim. Actions only.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/f09/gtk-orca'


def main(payload):
    OUT.mkdir(parents=True, exist_ok=True)
    log = OUT / 'orca-debug.log'
    # The runner has no sound card; speech-dispatcher blocks on audio output
    # (run 41270340855 spoke three phrases, then stalled). A PulseAudio null
    # sink gives synthesized speech somewhere to go; nothing is listened to.
    audio = []
    for command in (['pulseaudio', '--start', '--exit-idle-time=-1'],
                    ['pactl', 'load-module', 'module-null-sink', 'sink_name=f09null'],
                    ['pactl', 'set-default-sink', 'f09null']):
        done = subprocess.run(command, capture_output=True, text=True)
        audio.append({'command': ' '.join(command), 'code': done.returncode, 'output': (done.stdout + done.stderr)[-300:]})
    (OUT / 'audio.json').write_text(json.dumps(audio, indent=2) + '\n', encoding='utf-8')
    orca = subprocess.Popen(['orca', '--replace', '--debug', '--debug-file=' + str(log)], stdout=subprocess.DEVNULL,
                            stderr=subprocess.STDOUT)
    ready = False
    for _ in range(60):
        if log.exists() and log.stat().st_size > 0:
            ready = True
            break
        time.sleep(1)
    time.sleep(5)
    env = dict(os.environ, F09_GTK_COMPACT_OUT='build/f09/gtk-orca/flow')
    flow = subprocess.run([sys.executable, str(ROOT / 'tests/f09_audit/gtk_compact.py'), str(payload)], cwd=ROOT,
                          env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    (OUT / 'flow.log').write_text(flow.stdout + '\n' + flow.stderr, encoding='utf-8')
    orca.terminate()
    try:
        orca.wait(30)
    except subprocess.TimeoutExpired:
        orca.kill()
    text = log.read_text(encoding='utf-8', errors='replace') if log.exists() else ''
    spoken = re.findall(r"SPEECH OUTPUT: '(.*?)'", text)
    joined = '\n'.join(spoken)
    expectations = [
        ('O-01', 'the main window is announced', 'EXReader Linux'),
        ('O-02', 'the import control is spoken by name', 'Import book'),
        ('O-03', 'a shelf row is spoken with its book title', 'F09 book'),
        ('O-04', 'the collections dialog is announced', 'Library collections'),
        ('O-05', 'the reading page is announced', 'Reading page'),
        ('O-06', 'Back to library is spoken by name', 'Back to library'),
    ]
    checks = [{'id': cid, 'expected': want, 'phrase': phrase, 'status': 'pass' if phrase in joined else 'fail'}
              for cid, want, phrase in expectations]
    report = {'source_sha': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
              'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'), 'screen_reader': 'Orca', 'orca_ready': ready,
              'spoken_lines': len(spoken), 'checks': checks,
              'accepted': ready and all(c['status'] == 'pass' for c in checks), 'human_listening_verified': False}
    (OUT / 'spoken.txt').write_text(joined + '\n', encoding='utf-8')
    (OUT / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False)[:3000], flush=True)


if __name__ == '__main__':
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'GitHub Actions only'
    main(Path(sys.argv[1]).resolve())
