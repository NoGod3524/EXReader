#!/usr/bin/env python3
"""Retain partial launch and sample evidence if a full-host scenario stalls."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path('tests/reader_perf_gtk').resolve()))
import sample

class RetainingSampler(sample.Sampler):
    def launch_once(self, index):
        try:
            return super().launch_once(index)
        finally:
            (self.output / 'partial-launches.json').write_text(json.dumps(self.launches, indent=2) + '\n')
            (self.output / 'partial-samples.json').write_text(json.dumps({'samples': self.results, 'plan': self.plan}, indent=2) + '\n')

sample.Sampler = RetainingSampler
sample.main()
