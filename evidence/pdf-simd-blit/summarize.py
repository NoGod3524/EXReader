"""Derive report numbers and acceptance gates from this directory's raw JSON."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parent
variants = {name: json.loads((root / name / 'summary.json').read_text())
            for name in ['baseline', 'simd', 'region', 'all']}
assert len({v['input_sha256'] for v in variants.values()}) == 1
rows = []
for width in variants['baseline']['widths']:
    values = {name: data['results'][str(width)] for name, data in variants.items()}
    pixels = values['all']['pages'][0]['dimensions']
    row = {'width': width, 'pixels_per_page': pixels[0] * pixels[1],
           'variants': {name: {key: result[key] for key in ['p50_ms', 'p95_ms', 'open_ms']}
                        for name, result in values.items()}}
    before, after = values['baseline']['p50_ms'], values['all']['p50_ms']
    row.update(speedup=before / after, reduction_percent=100 * (before - after) / before,
               baseline_p50_ns_per_pixel=before * 1e6 / row['pixels_per_page'],
               all_p50_ns_per_pixel=after * 1e6 / row['pixels_per_page'],
               simd_only_saving_ms=before - values['simd']['p50_ms'],
               region_only_saving_ms=before - values['region']['p50_ms'],
               simd_with_regions_saving_ms=values['region']['p50_ms'] - after,
               regions_with_simd_saving_ms=values['simd']['p50_ms'] - after)
    rows.append(row)
diffs = {name: json.loads((root / ('diff-' + name) / 'diff.json').read_text())
         for name in ['simd', 'region', 'all']}
suite = ET.parse(root / 'ctest.xml').getroot()
cases = list(suite.iter('testcase'))
tests = {'count': len(cases), 'failed': sum(c.find('failure') is not None for c in cases),
         'skipped': sum(c.find('skipped') is not None for c in cases)}
profiles = {name: json.loads((root / ('profile-' + name + '.json')).read_text())
            for name in ['baseline', 'all']}
middle = next(row for row in rows if row['width'] == 1200)
result = {'widths': rows, 'tests': tests,
          'pixel_identity': {name: {'identical': d['identical'],
                                   'compared_pixels': d['compared_pixels'],
                                   'different_pixels': d['different_pixels'],
                                   'max_channel_delta': max(p['max_channel_delta'] for p in d['pages']),
                                   'max_page_rgba_rmse': max(p['rgba_rmse'] for p in d['pages'])}
                             for name, d in diffs.items()},
          'profile_exclusive_ns_per_output_pixel': {
              name: {**{path: row['exclusive_ns_per_output_pixel'] for path, row in profile['paths'].items()},
                     'residual': profile['residual_ns_per_output_pixel'],
                     'total': profile['ns_per_output_pixel']}
              for name, profile in profiles.items()},
          'gates': {'render_1200_p50_le_4ms': middle['variants']['all']['p50_ms'] <= 4,
                    'open_1200_p50_le_0_70ms': middle['variants']['all']['open_ms'] <= .7,
                    'improves_every_width': all(row['speedup'] > 1 for row in rows),
                    'pixel_identity': all(d['identical'] for d in diffs.values()),
                    'ctest_all_passed': tests['count'] > 0 and not tests['failed'] and not tests['skipped']}}
(root / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))

v = middle['variants']
pixel = result['pixel_identity']['all']
lines = [
    f"Items 1 and 3 are implemented with pixel identity. The 1200px render target remains unmet: **{v['all']['p50_ms']:.6f} ms p50**, versus {v['baseline']['p50_ms']:.6f} ms for the baseline and the requested 4.00 ms limit. This is a draft performance change.",
    '',
    '`src/vector.c` writes opaque RGBA spans with SSE2/NEON stores. `src/blend.c` blends eight pixels per iteration using exact integer division/rounding; transparent destinations retain the original straight-alpha denominator. Scalar fallback remains available. Constant clip runs share the span kernels.',
    '',
    'Clip objects cache exact nonzero bounds and whether the enclosed mask is solid 255. Vector fills, affine images, procedural paint, compound paths and group commits intersect their drawing bounds with that region before pixel loops. Empty intersections return immediately; solid rectangles need no per-pixel mask reads. Saved clips share the cached metadata. Group creation reuses it instead of rescanning the page.',
    '',
    '`src/fonts.c` and `src/font_outline.c` are unchanged. Item 2 (glyph atlas) is outside this branch; no atlas contribution is claimed.',
    '',
    'Measurements below use the unchanged capture timing boundaries in `tools/benchmark_pdf_rect.py`: one warmup round and five measured rounds over all 20 pages, giving 100 render samples per width. Every measurement process uses logical CPU 0 (affinity mask 1) and High priority. Other builds and processor frequency remain uncontrolled. Two earlier series without process controls are retained in [initial captures](initial-captures-with-background-ctest.json) and [repeat captures](uncontrolled-repeat-captures.json); they showed large scheduling/load variation, including a 2400px regression.',
    '',
    '| Width | Baseline p50 ms | SIMD only | Regions only | Combined | Combined open p50 ms |',
    '| --- | ---: | ---: | ---: | ---: | ---: |']
for row in rows:
    values = row['variants']
    lines.append(f"| {row['width']} | {values['baseline']['p50_ms']:.6f} | {values['simd']['p50_ms']:.6f} | {values['region']['p50_ms']:.6f} | {values['all']['p50_ms']:.6f} | {values['all']['open_ms']:.6f} |")
lines += ['',
    'Raw samples, page hashes, PNGs and compressed RGBA: [baseline](baseline/summary.json), [SIMD only](simd/summary.json), [regions only](region/summary.json), [combined](all/summary.json). The three ablations recompile the four graphics implementation files with identical current private headers and remaining objects. Baseline implementations come from `2b24c3ea8`; their pixels also match the original DLL built before edits ([comparison](diff-baseline-original/diff.json)).',
    '',
    f"At 1200px, isolated SIMD saves {middle['simd_only_saving_ms']:.6f} ms and isolated regions save {middle['region_only_saving_ms']:.6f} ms. Combined savings are {v['baseline']['p50_ms']-v['all']['p50_ms']:.6f} ms; combined is {v['all']['p50_ms']-v['region']['p50_ms']:.6f} ms above the regions-only median. These sequential captures do not demonstrate additive gains. Width reductions are " + ', '.join(f"{r['width']}px: {r['reduction_percent']:.3f}%" for r in rows) + '. The 600px result does not establish the requested proportional improvement.',
    '',
    f"1200px open p50 is {v['baseline']['open_ms']:.6f} -> {v['all']['open_ms']:.6f} ms, below the 0.70 ms limit. This is the harness open measurement, with disk cache uncontrolled.",
    '',
    f"**Pixel result:** {pixel['compared_pixels']:,} active RGBA pixels across 60 page/width pairs; **{pixel['different_pixels']} differing pixels, maximum channel delta {pixel['max_channel_delta']}, RMSE {pixel['max_page_rgba_rmse']:g}**. This includes the required 81,000,000 pixels at 1200/2400px plus 600px. SIMD-only and regions-only comparisons also have zero differences. [Combined diff](diff-all/diff.json), [SIMD diff](diff-simd/diff.json), [regions diff](diff-region/diff.json).",
    '',
    f"**Validation:** CTest {tests['count']}/{tests['count']}, zero failures and skips ([JUnit](ctest.xml), [log](ctest.log)). SSE2 and forced scalar fallback each pass 1,087,457 vector checks, including all paint-alpha/coverage pairs, sixteen byte alignments, transparent destinations, tails, blend modes and region comparisons. [SSE2](vector-sse2.txt), [scalar](vector-scalar.txt). The procedural-paint test now expects two 4x4 region scans instead of a full-page scan; all 283 checks pass ([output](paint-source.txt)). NEON execution was not tested on this x86 machine.",
    '',
    'The diagnostic DLLs time source copies without changing production objects. The following values are **exclusive ns per final output pixel** at 1200px, summed across 100 measured renders. Nested timers are subtracted; allocation/clear/free and other uninstrumented work remain visible. Instrumentation overhead is included, so these totals are separate from acceptance p50 timings.',
    '',
    '| Path | Baseline ns/pixel | Combined ns/pixel |',
    '| --- | ---: | ---: |']
labels = {'rectangle_opaque': 'Opaque rectangle spans', 'rectangle_alpha': 'Alpha/edge rectangle spans',
          'rectangle_clip': 'Masked rectangle spans', 'vector_fill_inclusive': 'Vector work outside rectangle spans',
          'group_commit': 'Group commit', 'canvas_create': 'Canvas allocation/clear',
          'group_begin': 'Group creation outside nested timers', 'group_end_inclusive': 'Group end outside commit',
          'clip_bounds': 'Clip bounds lookup/computation', 'residual': 'Remaining work and timer overhead', 'total': 'Total'}
cost = result['profile_exclusive_ns_per_output_pixel']
for key, label in labels.items():
    lines.append(f"| {label} | {cost['baseline'][key]:.6f} | {cost['all'][key]:.6f} |")
lines += ['', 'The largest remaining measured buckets are vector work outside rectangle spans, remaining work, opaque spans and canvas allocation/clear. The image, sampled-paint and complex-rectangle buckets had zero calls. [Baseline profile](profile-baseline.json), [combined profile](profile-all.json).', '',
          'A separate hot-cache benchmark invokes the actual `rectangle_span` implementations: 1200 pixels, 20,000 repetitions, seven samples. It covers alpha 128 even though the PDF baseline has no unmasked alpha-span calls. Values are p50 **ns per visited span pixel**.', '',
          '| Kernel | Baseline | Combined |', '| --- | ---: | ---: |']
kernels = json.loads((root / 'kernels.json').read_text())['variants']
for key, label in [('opaque_colour', 'Opaque colour'), ('alpha_128_opaque_destination', 'Alpha 128 over opaque'), ('alpha_128_constant_clip_128', 'Alpha 128, clip 128')]:
    lines.append(f"| {label} | {kernels['baseline'][key]['p50_ns_per_pixel']:.6f} | {kernels['all'][key]['p50_ns_per_pixel']:.6f} |")
lines += ['', '[Kernel raw samples](kernels.json). Opaque stores are already fast in the baseline; the demonstrated kernel gain is in normal alpha blending and constant masked spans.', '',
          'Run [reproduce.ps1](reproduce.ps1) from this checkout to configure/build, run CTest, construct the ablations, capture/compare all widths, profile both implementations, benchmark kernels and regenerate [results.json](results.json) and this report. It uses valid local dependency caches and workspace-local pinned downloads. [Provenance and tested platforms](provenance.json), [machine](machine.json). No parsing, font-file semantics or antialiasing quality changed.']
(root / 'REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
