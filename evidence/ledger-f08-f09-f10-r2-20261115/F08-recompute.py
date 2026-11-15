# SPDX-License-Identifier: MIT
"""Recompute F08 Windows-runner render p50/p95 from the tracked raw samples of run 43677041326."""
import json, math, ntpath, statistics, sys
d = json.load(open(sys.argv[1], encoding='utf-8'))
print('source=%s scope=%s display_present_frame=%s first_interactive=%s accepted=%s' % (
    d['source'], d['scope'], d['display_present_frame'], d['first_interactive'], d['accepted']))
for b in d['books']:
    s = sorted(x for p in b['candidate'] for x in p['metrics']['raw_render_ms'])
    print('%s n=%d p50_ms=%.6f p95_ms=%.6f peak_ws=%d exits=%s' % (
        ntpath.basename(b['path']), len(s), statistics.median(s),
        s[math.ceil(.95 * len(s)) - 1], max(p['metrics']['peak_working_set_bytes'] for p in b['candidate']),
        [p['exit'] for p in b['baseline'] + b['candidate']]))
