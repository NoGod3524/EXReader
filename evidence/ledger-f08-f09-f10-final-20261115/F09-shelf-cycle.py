# SPDX-License-Identifier: MIT
"""Print the real-SendInput Tab cycle observed on the shelf surface (last surface collected).

Standard library only. Usage: python F09-shelf-cycle.py <f09-keyboard dir>
The shelf phase starts at the first focus observation named
系列、标签与阅读统计 (the shelf view; it is only shown on the shelf surface);
the cycle is the sequence of distinct names until the first repeat.
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
events = [json.loads(line) for line in (Path(sys.argv[1]) / 'key-trace.jsonl').read_text(encoding='utf-8').splitlines() if line]
names = [(e['payload'].get('element') or {}).get('name') for e in events if e['kind'] == 'keyboard_focus_observed']
start = names.index('系列、标签与阅读统计')
shelf = names[start:]
cycle = []
for name in shelf:
    if name in cycle:
        break
    cycle.append(name)
longest, run, last = 0, 0, None
for name in shelf:
    run = run + 1 if name == last else 1
    last = name
    longest = max(longest, run)
print('shelf_observations=%d distinct_stops=%d longest_same_element_run=%d' % (len(shelf), len(cycle), longest))
print('cycle=%s' % cycle)
print('wraps=%s' % (len(shelf) > len(cycle) and shelf[len(cycle)] == cycle[0]))
