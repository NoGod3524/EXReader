#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Summarize EXR_PROFILE_IMAGE CSV; timings are sampled, not render benchmarks."""
import argparse
import csv
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    rows = [[float(v) for v in row] for row in csv.reader(args.input.open())]
    result = {}
    for width in sorted({int(r[0]) for r in rows}):
        group = [r for r in rows if r[0] == width]
        raw, corrected = [0.] * 4, [0.] * 4
        pixels = sum(r[8] for r in group)
        for r in group:
            if not r[9]:
                continue
            counts = [r[10], r[10] if r[4] else 0, r[10] if r[4] else 0, r[9]]
            for i in range(4):
                raw[i] += r[11+i] / r[16] * 1e9 * r[8] / r[9]
                corrected[i] += max(0, r[11+i] - counts[i]*r[17]) / r[16] * 1e9 * r[8] / r[9]
        result[width] = {
            'draws': len(group), 'covered_destination_pixels': int(pixels),
            'sampled_destination_pixels': int(sum(r[9] for r in group)),
            'instrumented_loop_ns_per_pixel': sum(r[15]/r[16]*1e9 for r in group)/pixels,
            'clock_pair_ns': sum(r[17]/r[16]*1e9 for r in group)/len(group),
            'stages': {name: {'raw_ns_per_pixel': raw[i]/pixels,
                              'corrected_ns_per_pixel': corrected[i]/pixels,
                              'raw_percent': raw[i]/sum(raw)*100 if sum(raw) else None,
                              'corrected_percent': corrected[i]/sum(corrected)*100 if sum(corrected) else None}
                       for i, name in enumerate(['source_sample', 'mask_sample', 'mask_matte_apply', 'pack_composite'])},
            'paths': [list(path) for path in sorted({tuple(int(v) for v in r[1:8]+r[18:22]) for r in group})],
            'path_columns': ['source_width', 'source_height', 'interpolate', 'mask', 'has_matte',
                             'state', 'state_depth', 'mask_interpolate', 'mask_width', 'mask_height', 'blend_mode'],
        }
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
