"""Compile the production image_byte/image_rgb text against the quotient form.

The two functions are cut verbatim from src/affine_image.c into a test
program. Random premultiplied sums, rounding-boundary sums (t=k+.5 and its
neighbouring doubles), bilinear 2x/3x/4x weights, integer nearest sums,
tiny/huge alpha and non-finite edge values are each compared with
image_byte(sums[k]/sums[3]), as are out-of-domain lanes (negative, at or
above 2^31, NaN) that must take the scalar loop. Every compiler variant must
report 0 mismatches; the unguarded negative control must report some.
"""
from pathlib import Path
import json
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent

DRIVER = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#if defined(__SSE2__) || defined(_M_X64)
#include <emmintrin.h>
#endif
FUNCTIONS
static uint32_t quotient(const double s[4]) {
  uint32_t c=0; for(unsigned k=0;k<3;k++) c|=image_byte(s[k]/s[3])<<(24-8*k); return c;
}
static uint64_t state=0x9e3779b97f4a7c15ull;
static uint64_t next(void) { state^=state<<13; state^=state>>7; state^=state<<17; return state; }
static double unit(void) { return (next()>>11)*0x1p-53; }
static unsigned long long checked,mismatched;
static void check(const double s[4]) {
  uint32_t a=image_rgb(s),b=quotient(s);
  checked++;
  if(a!=b) { if(mismatched<10) printf("MISMATCH %.17g %.17g %.17g %.17g -> %08x %08x\n",s[0],s[1],s[2],s[3],a,b); mismatched++; }
}
int main(void) {
  double s[4]; unsigned long long i;
  /* 1. Random bilinear supersample sums: four subsamples, four taps each. */
  for(i=0;i<20000000ull;i++) {
    double r=0,g=0,b=0,a=0; unsigned n=1+(unsigned)(next()%4);
    for(unsigned q=0;q<n;q++) {
      double wx=unit(),wy=unit(),w[4]={(1-wx)*(1-wy),wx*(1-wy),(1-wx)*wy,wx*wy};
      for(unsigned t=0;t<4;t++) {
        uint64_t p=next(); unsigned pa=(next()%3==0) ? 255 : (unsigned)(p>>24&255);
        double aw=pa*w[t]; r+=(p&255)*aw; g+=(p>>8&255)*aw; b+=(p>>16&255)*aw; a+=aw;
      }
    }
    if(!a) continue;
    s[0]=r;s[1]=g;s[2]=b;s[3]=a; check(s);
  }
  /* 2. Exact rounding boundaries t=k+.5 and their neighbouring doubles. */
  for(unsigned k=0;k<256;k++) for(i=0;i<20000;i++) {
    double a=1e-3+unit()*1020,t=k+.5,x=t*a;
    double v[5]={x,nextafter(x,0),nextafter(x,1e300),nextafter(nextafter(x,0),0),nextafter(nextafter(x,1e300),1e300)};
    for(unsigned j=0;j<5;j++) { s[0]=v[j];s[1]=v[(j+1)%5];s[2]=v[(j+2)%5];s[3]=a; check(s); }
  }
  /* 3. Integer channels at fixed bilinear weights (2x, 3x, 4x magnification). */
  { const double weights[]={0,.25,.5,.75,1,1./3,2./3,1./6,5./6,.125,.375,.625,.875};
    for(i=0;i<20000000ull;i++) {
      double wx=weights[next()%13],wy=weights[next()%13],w[4]={(1-wx)*(1-wy),wx*(1-wy),(1-wx)*wy,wx*wy},r=0,g=0,b=0,a=0;
      for(unsigned q=0;q<4;q++) for(unsigned t=0;t<4;t++) {
        uint64_t p=next(); unsigned pa=(next()%2) ? 255 : (unsigned)(p>>24&255);
        double aw=pa*w[t]; r+=(p&255)*aw; g+=(p>>8&255)*aw; b+=(p>>16&255)*aw; a+=aw;
      }
      if(!a) continue;
      s[0]=r;s[1]=g;s[2]=b;s[3]=a; check(s);
    } }
  /* 4. Nearest-neighbour integer sums: up to four texels, alpha 1..255. */
  for(i=0;i<20000000ull;i++) {
    uint32_t r=0,g=0,b=0,a=0; unsigned n=1+(unsigned)(next()%4);
    for(unsigned q=0;q<n;q++) { uint64_t p=next(); unsigned pa=(unsigned)(p>>24&255); r+=(p&255)*pa; g+=(p>>8&255)*pa; b+=(p>>16&255)*pa; a+=pa; }
    if(!a) continue;
    s[0]=r;s[1]=g;s[2]=b;s[3]=a; check(s);
  }
  /* 5. Extreme alpha magnitudes and edge values. */
  { const double alphas[]={0x1p-1074,0x1p-1060,0x1p-1030,0x1p-1023,0x1p-1022,0x1p-1000,1e-300,1e-30,1e-10,1,255,1020,1e10,1e300,INFINITY};
    for(unsigned j=0;j<sizeof alphas/sizeof *alphas;j++) for(i=0;i<200000;i++) {
      double a=alphas[j],c[3];
      for(unsigned k=0;k<3;k++) { unsigned m=(unsigned)(next()%4); c[k]=m==0 ? 0 : m==1 ? a*255 : m==2 ? a*(unit()*255) : a*((next()%256)+.5); }
      s[0]=c[0];s[1]=c[1];s[2]=c[2];s[3]=a; check(s);
    } }
  /* 6. Out-of-domain lanes the renderer never produces: negative sums,
     quotients at or above 2^31 and 2^63, and NaN. */
  { const double odd[]={-1e300,-3e9,-256.5,-1.5,-1,-.75,-.5,-0.,0,255.49,255.5,256,1e6,0x1p31-1,0x1p31-.5,0x1p31,3e9,0x1p32,0x1p63,1e19,1e300,INFINITY,-INFINITY,NAN};
    const double alphas[]={1,-1,255,1020,1e-300,0x1p-1074};
    const unsigned n=sizeof odd/sizeof *odd;
    for(unsigned j=0;j<sizeof alphas/sizeof *alphas;j++) for(unsigned x=0;x<n;x++) for(unsigned y=0;y<n;y++) for(unsigned z=0;z<n;z++) {
      double a=alphas[j]; s[0]=odd[x]*a;s[1]=odd[y]*a;s[2]=odd[z]*a;s[3]=a; check(s);
    } }
  printf("{\"checked\":%llu,\"mismatched\":%llu}\n",checked,mismatched);
  return mismatched!=0;
}
'''


def functions():
    text = (ROOT / 'src/affine_image.c').read_text(encoding='utf-8')
    byte = re.search(r'static uint32_t image_byte\(double value\) \{.*?\n\}\n', text, re.S).group(0)
    rgb = re.search(r'static inline uint32_t image_rgb\(const double sums\[4\]\) \{.*?\n\}\n', text, re.S).group(0)
    return byte + rgb


def main():
    source = DRIVER.replace('FUNCTIONS', functions())
    variants = {
        'release': ['-O3', '-DNDEBUG', '-std=c11'],
        'contract-fast-fma': ['-O3', '-DNDEBUG', '-std=gnu11', '-ffp-contract=fast', '-mfma', '-mavx2'],
        'scalar-no-sse2-path': ['-O3', '-DNDEBUG', '-std=c11', '-U__SSE2__', '-mno-sse3'],
    }
    # Negative control: without the sign-bit guard the saturating packs must
    # disagree with image_byte on some out-of-domain lanes (section 6).
    # Variant E guards with the sign mask; variant F with the boundary mask.
    control = source.replace('if(!_mm_movemask_ps(_mm_castsi128_ps(q)))', 'if(1)')
    control = control.replace('if((_mm_movemask_pd(ok)&(_mm_movemask_pd(okb)|2))==3)', 'if(1||(_mm_movemask_pd(ok)&_mm_movemask_pd(okb)))')
    assert control != source
    results = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name, flags in [*variants.items(), ('negative-control-no-guard', variants['release'])]:
            c_path = Path(tmp) / f'{name}.c'
            c_path.write_text(control if name.startswith('negative') else source)
            exe = Path(tmp) / f'{name}.exe'
            subprocess.run(['gcc', *flags, '-Wall', '-Wextra', '-Werror', str(c_path), '-o', str(exe), '-lm'], check=True)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            last = run.stdout.strip().splitlines()[-1]
            results[name] = {'flags': flags, 'exit': run.returncode, **json.loads(last),
                             'first_mismatches': run.stdout.strip().splitlines()[:-1]}
            print(name, results[name]['checked'], results[name]['mismatched'], flush=True)
    (OUT / (f'equivalence-{sys.argv[1]}.json' if len(sys.argv) > 1 else 'equivalence.json')).write_text(json.dumps(results, indent=2) + '\n')
    passed = all(r['exit'] == 0 and r['mismatched'] == 0 for n, r in results.items() if not n.startswith('negative'))
    detected = results['negative-control-no-guard']['mismatched'] > 0
    return 0 if passed and detected else 1


if __name__ == '__main__':
    sys.exit(main())
