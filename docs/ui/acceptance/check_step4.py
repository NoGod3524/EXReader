# SPDX-License-Identifier: MIT
"""Host paint/cache acceptance; all windows offscreen, all children consoleless.
Usage: python docs/ui/acceptance/check_step4.py EXE FONT SAMPLE_DIR NEW_OUTPUT
"""
import ctypes as c
import ctypes.wintypes as w
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
USER = c.WinDLL('user32', use_last_error=True)
USER.GetForegroundWindow.restype = w.HWND
USER.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]
USER.GetWindowRect.argtypes = [w.HWND, c.POINTER(w.RECT)]
USER.SetProcessDpiAwarenessContext.argtypes = [w.HANDLE]
USER.SetProcessDpiAwarenessContext(w.HANDLE(-4))  # inspect physical window coordinates


def run(exe, args, out, trace=None):
    env = dict(os.environ)
    for key in ('EXR_PAINT_TRACE', 'EXR_PAINT_REPEAT', 'EXR_PAINT_MARKER'):
        env.pop(key, None)
    if trace:
        env['EXR_PAINT_TRACE'] = str(trace)
    process = subprocess.Popen([str(exe), *map(str, args)], env=env,
                               creationflags=subprocess.CREATE_NO_WINDOW,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    observations = 0
    positions = set()
    started = time.monotonic()
    callback_type = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)

    def inspect(hwnd, _):
        owner = w.DWORD()
        USER.GetWindowThreadProcessId(hwnd, c.byref(owner))
        if owner.value == process.pid:
            name = c.create_unicode_buffer(64)
            USER.GetClassNameW(hwnd, name, 64)
            if name.value == 'EXReaderHost':
                rect = w.RECT()
                USER.GetWindowRect(hwnd, c.byref(rect))
                positions.add((rect.left, rect.top))
        return True

    callback = callback_type(inspect)
    try:
        while process.poll() is None:
            owner = w.DWORD()
            USER.GetWindowThreadProcessId(USER.GetForegroundWindow(), c.byref(owner))
            observations += owner.value == process.pid
            USER.EnumWindows(callback, 0)
            if observations or positions - {(-32000, -32000)}:
                raise RuntimeError(f'host activated or left the offscreen position: foreground={observations}, positions={positions}')
            if time.monotonic() - started > 240:
                raise TimeoutError(str(out))
            time.sleep(.02)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait()
    result = dict(exit=process.returncode, foreground_observations=observations,
                  positions=sorted(positions), elapsed_seconds=time.monotonic()-started)
    (out/'process.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    assert process.returncode == 0, result
    return result


def segment(rows, begin, end):
    a = next(i for i, row in enumerate(rows) if row[0] == begin)
    b = next(i for i, row in enumerate(rows[a+1:], a+1) if row[0] == end)
    return rows[a+1:b]


def values(rows, key):
    return [value for name, _, value in rows if name == key]


def analyze(rows, shell):
    active = segment(rows, 'probe_begin', 'probe_end')
    totals = {name[6:]: int(value) for name, _, value in active if name.startswith('total_')}
    assert totals['presented'] > 0 and totals['blank'] == totals['stale_size'] == totals['present_failed'] == 0, totals
    assert len(values(active, 'presented')) == totals['presented']
    assert sum(values(active, 'blank')) == sum(values(active, 'stale_size')) == 0
    assert totals['bitblt'] > 0 and (not shell or totals['stretch'] == 0), totals
    assert values(active, 'present_client_w') == values(active, 'present_buffer_w')
    assert values(active, 'present_client_h') == values(active, 'present_buffer_h')
    if shell:
        assert values(active, 'present_page_w') == values(active, 'present_expected_w')
        assert values(active, 'present_page_h') == values(active, 'present_expected_h')
    keys = segment(active, 'keys_begin', 'keys_end')
    wheel = segment(active, 'wheel_begin', 'wheel_end')
    assert len(values(keys, 'key')) == 20 and len(values(wheel, 'wheel')) == 100
    for group in (keys, wheel):
        assert values(group, 'presented') and sum(values(group, 'blank')) == 0
    cache = segment(active, 'cache_begin', 'cache_end')
    layouts, renders = values(cache, 'cache_layout_delta'), values(cache, 'cache_render_delta')
    assert len(layouts) >= 20 and len(renders) == len(layouts) and sum(layouts) == sum(renders) == 0
    cold = segment(active, 'cold_begin', 'cold_end') if shell else []
    samples, stage, hit = [], None, False
    for name, _, value in cold:
        if name == 'sdk_job_begin':
            stage, hit = {}, False
        elif name == 'cache_hit':
            hit = True
        elif stage is not None and name.startswith('stage_'):
            stage[name] = value
        elif name == 'sdk_job_end' and stage is not None:
            if not hit and stage.get('stage_raster_ms', 0) > 0:
                samples.append(stage['stage_anchor_pager_ms'] + stage['stage_raster_ms'])
            stage = None
    result = dict(totals=totals, page_down=20, wheel_detents=100,
                  keys_presented=len(values(keys, 'presented')), wheel_presented=len(values(wheel, 'presented')),
                  cache_hits=len(layouts), cache_layout_deltas=layouts, cache_render_deltas=renders,
                  layout_calls_start_end=values(active, 'layout_calls'),
                  render_calls_start_end=values(active, 'render_calls'))
    if shell:
        assert len(samples) >= 40, samples
        result['miss_samples_ms'] = samples
        result['miss_p95_ms'] = sorted(samples)[math.ceil(len(samples)*.95)-1]
    return result


def first_line(layout):
    start, end = layout['lines'][0][:2]
    base = layout['range'][0]
    return layout['text'].encode('utf-8')[start-base:end-base].decode('utf-8')


def negative_checks(rows, shell):
    rejected = []
    for event, value in [('total_presented', 0), ('total_blank', 1),
                         ('cache_layout_delta', 1), ('present_buffer_w', -1)]:
        bad = [(name, stamp, value if name == event else actual) for name, stamp, actual in rows]
        try:
            analyze(bad, shell)
        except AssertionError:
            rejected.append(event)
        else:
            raise AssertionError('analyzer accepted corrupt evidence: '+event)
    return rejected


def scenario(exe, font, book, out, width, height, shell):
    out.mkdir()
    steps = [f'import|{book}', 'open|EXReader benchmark', 'wait_idle']
    if shell:
        steps += ['shell|on', 'shell_dpi|96', 'shell_font|18', f'shell_client|{width}|{height}', 'wait_idle']
    steps += ['probe_wait|1000', 'probe_begin']
    if shell:
        # Consecutive single-page requests precede the existing 150 ms prefetch
        # timer. Count only jobs which actually rasterize; never disable prefetch.
        steps += ['probe_mark|cold_begin'] + ['probe_key']*60 + ['probe_mark|cold_end']
    steps += ['probe_mark|keys_begin'] + ['probe_key', 'probe_wait|400', 'wait_idle']*20
    steps += ['probe_mark|keys_end', 'probe_mark|cache_begin']
    steps += ['probe_move|-1', 'wait_idle', 'probe_move|1', 'wait_idle']*10
    steps += ['probe_mark|cache_end', 'probe_mark|wheel_begin', 'probe_wheel_burst', 'wait_idle',
              'probe_wait|500', 'probe_mark|wheel_end']
    if shell:
        steps += ['shell_measure|before', 'snapshot|before', 'probe_mark|resize_begin',
                  'shell_client|720|560', 'shell_measure|small', 'snapshot|small',
                  'shell_client|2560|1440', 'shell_measure|large', 'snapshot|large',
                  f'shell_client|{width}|{height}', 'shell_measure|restored', 'snapshot|restored',
                  'delay|700', 'resize|1100|750', 'probe_wait|250', 'resize|1200|850',
                  'probe_wait|200', 'resize|1500|1000', 'wait_idle', 'delay|0',
                  f'shell_client|{width}|{height}', 'shell_measure|busy-restored', 'snapshot|busy-restored',
                  'probe_mark|resize_end']
    steps += ['probe_end', 'quit']
    script = out/'run.drive'
    script.write_text('\n'.join(steps)+'\n', encoding='utf-8')
    trace = out/'paint.csv'
    process = run(exe, ['--offscreen', '--font', font, '--drive', script, '--data', out/'profile', '--evidence', out], out, trace)
    log = (out/'drive.log').read_text(encoding='utf-8')
    failures = [line for line in log.splitlines() if line.startswith('STEP\t') and '\tFAIL\t' in line]
    assert not failures, failures
    rows = [(name, float(stamp), float(value)) for name, stamp, value in
            (line.split(',') for line in trace.read_text().splitlines())]
    result = analyze(rows, shell)
    result['rejected_negative_evidence'] = negative_checks(rows, shell)
    result['process'] = process
    if shell:
        from PIL import Image, ImageChops
        layouts = {name: json.loads((out/(name+'.json')).read_text(encoding='utf-8'))
                   for name in ('before', 'small', 'large', 'restored', 'busy-restored')}
        before = layouts['before']
        assert before['client'] == [width, height] and before['lines']
        for name, layout in layouts.items():
            assert layout['epoch'] == layout['frame_epoch'] and layout['display'] == layout['page']
            if name in ('restored', 'busy-restored'):
                assert layout['range'] == before['range'] and first_line(layout) == first_line(before)
        images = {}
        for name, layout in layouts.items():
            x, y, _, _ = layout['client_box']
            dx, dy = layout['origin']
            pw, ph = layout['page']
            with Image.open(out/(name+'.png')) as image:
                images[name] = image.convert('RGB').crop((x+dx,y+dy,x+dx+pw,y+dy+ph))
            assert images[name].getextrema() != ((255,255),)*3, name
        diffs = {name: sum(pixel != (0,0,0) for pixel in ImageChops.difference(images['before'], images[name]).getdata())
                 for name in ('restored', 'busy-restored')}
        assert not any(diffs.values()), diffs
        result['resize'] = dict(first_line_before=first_line(before),
                                first_line_restored=first_line(layouts['restored']),
                                first_line_busy_restored=first_line(layouts['busy-restored']),
                                page_pixel_differences=diffs,
                                pages={name: layout['page'] for name,layout in layouts.items()},
                                range_before_restored=[before['range'],layouts['restored']['range']])
        result['pass'] = result['miss_p95_ms'] <= (25 if width == 1280 else 35)
    (out/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(out.name, 'PASS' if result.get('pass', True) else 'FAIL', result.get('miss_p95_ms'), result['totals'], flush=True)
    # Keep collecting the other hard criteria even when a latency limit fails.
    return result


def main():
    exe, font, sample, out = map(lambda arg: Path(arg).resolve(), sys.argv[1:])
    out.mkdir()  # refuse to overwrite previous measurements
    sys.path.insert(0, str(ROOT/'tools'))
    spec = importlib.util.spec_from_file_location('fixtures', ROOT/'tools/run_benchmarks.py')
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    book = out/'Long-acceptance.epub'
    fixtures.make_epub(book, 3, 163840, single_paragraph=True)  # PR #43 input
    result = {'scenarios': {}}
    for name, width, height, shell in [('shell-1280',1280,800,True), ('shell-2560',2560,1440,True), ('legacy',1280,800,False)]:
        result['scenarios'][name] = scenario(exe,font,book,out/name,width,height,shell)
    dest = out/'selftest'
    dest.mkdir()
    process = run(exe, ['--self-test', font, sample/'Sample.epub', sample/'Sample.pdf', dest/'report.json', dest/'page.png'], dest)
    report = json.loads((dest/'report.json').read_text(encoding='utf-8'))
    assert report['passed'] and report['checks'] == 26, report
    result['selftest'] = dict(process=process, report=report)
    runtime = next(path for path in (exe.parent/'libexreader.dll',exe.parent/'exreader.dll') if path.exists())
    result['sha256'] = {str(path):hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in (exe,runtime,font,book)}
    result['pass'] = all(row.get('pass', True) for row in result['scenarios'].values())
    (out/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('ALL PASS' if result['pass'] else 'LATENCY ACCEPTANCE FAILED', flush=True)
    return 0 if result['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
