#!/usr/bin/env python3
"""Retain partial launch and sample evidence if a full-host scenario stalls."""
import json
import hashlib
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path('tests/reader_perf_gtk').resolve()))
import sample

# The wave-3 host's native minimum width is 1088 px; retain a fixed viewport.
sample.WINDOW_WIDTH = 1088

class RetainingSampler(sample.Sampler):
    def collect_environment(self):
        super().collect_environment()
        probe = Path(os.environ['EXR_FRAME_PROBE']).resolve(strict=True)
        raw = self.output / 'frame-clock-raw'
        raw.mkdir()
        self.environment['host_environment']['LD_PRELOAD'] = str(probe)
        self.environment['host_environment']['EXR_FRAME_TRACE_DIR'] = str(raw)
        self.environment['frame_clock_instrument'] = {
            'library': str(probe), 'sha256': hashlib.sha256(probe.read_bytes()).hexdigest(),
            'scope': 'GDK after-paint clock; instrumented Xvfb process, not display presentation',
        }
        self.write_environment()

    def launch_once(self, index):
        try:
            return super().launch_once(index)
        finally:
            (self.output / 'partial-launches.json').write_text(json.dumps(self.launches, indent=2) + '\n')
            (self.output / 'partial-samples.json').write_text(json.dumps({'samples': self.results, 'plan': self.plan}, indent=2) + '\n')

sample.Sampler = RetainingSampler
sample.main()
