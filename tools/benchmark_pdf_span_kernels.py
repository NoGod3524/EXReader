#!/usr/bin/env python3
"""Measure actual rectangle_span kernels, including alpha absent from the PDF.

Compile baseline/current vector.c in separate executables; all other code and
compiler flags match. Buffers fit in cache; this is not a page render benchmark.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess

SOURCE = r'''
#include <windows.h>
#include "VECTOR_SOURCE"
int main(void) {
  enum { width=1200, repeats=20000, samples=7 };
  unsigned char pixels[width*4],mask[width];
  exr_bitmap b={width,1,width*4,pixels,4},clip={width,1,width,mask,1};
  LARGE_INTEGER frequency,start,end;unsigned kind,sample,i;
  if(AFFINITY_MASK && !SetProcessAffinityMask(GetCurrentProcess(),(DWORD_PTR)AFFINITY_MASK)) return 2;
  if(PRIORITY_CLASS && !SetPriorityClass(GetCurrentProcess(),PRIORITY_CLASS)) return 2;
  QueryPerformanceFrequency(&frequency);
  for(kind=0;kind<3;kind++) for(sample=0;sample<samples;sample++) {
    memset(pixels,255,sizeof(pixels));memset(mask,128,sizeof(mask));
    QueryPerformanceCounter(&start);
    for(i=0;i<repeats;i++) {
      rectangle_span(&b,0,width,0,255,
        kind ? 0x27b5ed80 : 0x27b5edff,NULL,0,kind==2 ? &clip : NULL,EXR_BLEND_NORMAL,NULL);
      __asm__ __volatile__("" : : "g"(pixels) : "memory");
    }
    QueryPerformanceCounter(&end);
    printf("%u %u %.12f %u\n",kind,sample,
      (end.QuadPart-start.QuadPart)*1e9/frequency.QuadPart/width/repeats,(unsigned)pixels[0]);
  }
  return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cpu-affinity', type=lambda s: int(s, 0))
    parser.add_argument('--priority', choices=['normal', 'high'])
    args = parser.parse_args()
    root, output = Path(__file__).resolve().parents[1], args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    result = {'scope': 'Hot-cache rectangle spans; 1200 pixels, 20000 repetitions, seven samples; ns per visited span pixel',
              'cpu_affinity': args.cpu_affinity, 'priority': args.priority, 'variants': {}}
    names = ['opaque_colour', 'alpha_128_opaque_destination', 'alpha_128_constant_clip_128']
    for name, vector in [('baseline', args.baseline_source.resolve() / 'src/vector.c'), ('all', root / 'src/vector.c')]:
        source, binary = output / (name + '.c'), output / (name + '.exe')
        source.write_text(SOURCE.replace('VECTOR_SOURCE', vector.as_posix())
                          .replace('AFFINITY_MASK', str(args.cpu_affinity or 0))
                          .replace('PRIORITY_CLASS', str({'normal': 0x20, 'high': 0x80}.get(args.priority, 0))), encoding='utf-8')
        command = ['gcc', '-O3', '-DNDEBUG', '-std=c11', '-I' + str(root / 'src'), '-I' + str(root / 'include'),
                   str(source), str(root / 'src/blend.c'), str(root / 'src/common.c'), str(root / 'src/icc.c'), '-lm', '-o', str(binary)]
        subprocess.run(command, check=True, capture_output=True)
        text = subprocess.check_output([str(binary)], text=True)
        (output / (name + '.txt')).write_text(text)
        rows = {key: [] for key in names}
        for line in text.splitlines():
            kind, sample, ns, pixel = line.split()
            rows[names[int(kind)]].append(float(ns))
        result['variants'][name] = {key: {'samples_ns_per_pixel': values,
                                         'p50_ns_per_pixel': statistics.median(values)} for key, values in rows.items()}
        result['variants'][name]['vector_sha256'] = hashlib.sha256(vector.read_bytes()).hexdigest()
        result['variants'][name]['binary_sha256'] = hashlib.sha256(binary.read_bytes()).hexdigest()
    (output / 'kernels.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
