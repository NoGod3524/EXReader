#!/usr/bin/env python3
"""Record GDK clock cadence without treating it as displayed-frame timing."""
import hashlib
import json
import os
from pathlib import Path
import sys

out = Path('build/full-gtk-evidence')
result = {'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
          'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'clock_samples_complete': False,
          'physical_presentation_measured': False, 'performance_accepted': False,
          'scope': 'instrumented GDK after-paint clock intervals on Xvfb; excludes display presentation and rendering duration',
          'launches': [], 'problems': []}
try:
    environment = json.loads((out / 'environment.json').read_text())
    assert environment['source_sha'] == result['source_sha']
    source = out / 'launches.json'
    launches = json.loads(source.read_text())['launches'] if source.exists() else json.loads((out / 'partial-launches.json').read_text())
    pids = [row.get('pid') for row in launches]
    assert all(isinstance(pid, int) and pid > 0 for pid in pids) and len(pids) == len(set(pids))
    result['probe'] = environment['frame_clock_instrument']
    for row in launches:
        path = out / 'frame-clock-raw' / (str(row['pid']) + '.tsv')
        clocks = {}
        if path.exists():
            for line in path.read_text().splitlines():
                clock, frame, received = line.split('\t')
                clocks.setdefault(clock, []).append([int(frame), int(received)])
        intervals = []
        for values in clocks.values():
            assert all(b[0] > a[0] and b[1] >= a[1] for a, b in zip(values, values[1:]))
            intervals.extend(b[0] - a[0] for a, b in zip(values, values[1:]))
        result['launches'].append({'launch': row['launch'], 'kind': row['kind'], 'pid': row['pid'],
                                   'after_paint_samples': sum(len(v) for v in clocks.values()),
                                   'intervals_us': intervals,
                                   'raw_sha256': hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None})
    result['clock_samples_complete'] = len(launches) == 32 and all(row['intervals_us'] for row in result['launches'])
    if not result['clock_samples_complete']:
        result['problems'].append('missing frame-clock intervals or incomplete 32-launch plan')
except (OSError, KeyError, ValueError, AssertionError) as exc:
    result['problems'].append(type(exc).__name__ + ': ' + str(exc))
out.mkdir(parents=True, exist_ok=True)
(out / 'frame-clock-observation.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
if not result['clock_samples_complete']:
    sys.exit('frame-clock observation incomplete; raw data preserved')
