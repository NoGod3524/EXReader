"""F09 Windows screen reader: what NVDA actually speaks on the compact host.

UI Automation results (windows_compact.py) say what an assistive client can
read; they are not a screen-reader result. This lane runs a real NVDA (the
official portable build, installed on the runner by the workflow) with speech
logging at the IO level, drives the same compact flow with real keys while
NVDA is running, then reads NVDA's own log. Each expectation is a phrase NVDA
must have spoken at that step. Human listening is a separate record that this
lane does not claim. Actions only.
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
OUT = ROOT / 'build/f09/windows-nvda'


def main(nvda, exe, book):
    OUT.mkdir(parents=True, exist_ok=True)
    config = OUT / 'nvda-config'
    config.mkdir(exist_ok=True)
    (config / 'nvda.ini').write_text(
        '[general]\n\tshowWelcomeDialogAtStartup = False\n\taskToExit = False\n'
        '\tplayStartAndExitSounds = False\n[update]\n\tautoCheck = False\n'
        '[keyboard]\n\tspeakTypedCharacters = False\n\tspeakTypedWords = False\n', encoding='utf-8')
    log = OUT / 'nvda.log'
    started = subprocess.Popen([str(nvda), '-m', '--log-level=12', '--log-file=' + str(log),
                                '--config-path=' + str(config)])
    ready = False
    for _ in range(90):
        if log.exists() and 'NVDA initialized' in log.read_text(encoding='utf-8', errors='replace'):
            ready = True
            break
        time.sleep(1)
    env = dict(os.environ, F09_WINDOWS_COMPACT_OUT='build/f09/windows-nvda/flow')
    flow = subprocess.run([sys.executable, str(ROOT / 'tests/f09_audit/windows_compact.py'), str(exe), str(book)],
                          cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    (OUT / 'flow.log').write_text(flow.stdout + '\n' + flow.stderr, encoding='utf-8')
    subprocess.run([str(nvda), '-q'], timeout=60)
    try:
        started.wait(60)
    except subprocess.TimeoutExpired:
        started.kill()
    text = log.read_text(encoding='utf-8', errors='replace') if log.exists() else ''
    spoken = [m.group(1) for m in re.finditer(r'Speaking \[(.*?)\]\s*$', text, re.M)]
    joined = '\n'.join(spoken)
    book_title = Path(book).stem
    expectations = [
        ('S-01', 'the main window title is spoken', 'EXReader'),
        ('S-02', 'the library menu is spoken by its name', '书库'),
        ('S-03', 'the import chooser is announced (system dialog title, runner locale)', ('打开', 'Open')),
        ('S-04', 'a shelf row is spoken with the book title', book_title[:12]),
        ('S-05', 'the reading menu is spoken', '阅读'),
        ('S-06', 'the saved note text is spoken', 'f09 keyboard note'),
    ]
    def heard(phrase):
        return any(p and p in joined for p in (phrase if isinstance(phrase, tuple) else (phrase,)))
    checks = [{'id': cid, 'expected': want, 'phrase': phrase, 'status': 'pass' if heard(phrase) else 'fail'}
              for cid, want, phrase in expectations]
    report = {'source_sha': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
              'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'), 'screen_reader': 'NVDA portable', 'nvda_ready': ready,
              'spoken_lines': len(spoken), 'checks': checks,
              'accepted': ready and all(c['status'] == 'pass' for c in checks),
              'human_listening_verified': False}
    (OUT / 'spoken.txt').write_text(joined + '\n', encoding='utf-8')
    (OUT / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False)[:3000], flush=True)


if __name__ == '__main__':
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'GitHub Actions only'
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
