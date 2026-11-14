"""Windows typography matrix; one generated host, unchanged product sources/DLL.

python -X utf8 tools/perf/typography_bench.py build --work <external-directory> --sdk-build <build>
python -X utf8 tools/perf/typography_bench.py run --work <same-directory> --output <evidence-directory> --capture <ops/capture_window.py>
python -X utf8 tools/perf/typography_bench.py summarize --output <evidence-directory>
"""
import argparse
import csv
import ctypes as C
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import random
import shutil
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
BASE = Path('C:/Users/Oscar/Documents/Codex')
FONTS = {'serif': Path('C:/Windows/Fonts/NotoSerifSC-VF.ttf'),
         'sans': BASE / 'exr-demo-2a/Reader.otf',
         'simsun': Path('C:/Windows/Fonts/simsun.ttc')}
BOOK = BASE / 'exr-cjk-corpus/hongloumeng-24264.epub'
VIEWPORTS = [(1242, 711), (1552, 928)]
LINE_HEIGHTS = [1.60, 1.75, 1.90]


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def identity(path):
    path = Path(path).resolve(strict=True)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=sha(path))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def execute(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', **kwargs).stdout


def system_times():
    values = [C.c_ulonglong() for _ in range(3)]
    assert C.windll.kernel32.GetSystemTimes(*(C.byref(v) for v in values))
    return [v.value for v in values]


def build(args):
    args.work.mkdir(parents=True, exist_ok=True)
    source = (ROOT / 'examples/reader.c').read_text(encoding='utf-8')
    edits = {
        'static int shell_drive_on, shell_legacy, shell_active;':
        'static int shell_drive_on, shell_legacy, shell_active;\nstatic float typography_line_height = 1.75f;',
        'config->page.line_height = SHELL_BODY_LINE_HEIGHT;':
        'config->page.line_height = typography_line_height;',
        'geometry.font*1.75f': 'geometry.font*typography_line_height',
        'static int drive_execute(void) {':
        '#include "typography_probe.inc"\nstatic int drive_execute(void) {',
        '  const char *action = drive_args[0];':
        '  const char *action = drive_args[0];\n'
        '  if (!strcmp(action,"typography_count")) { drive_step_finish(typography_count(),"whole-book pagination counted"); return 0; }',
        '  host_probe_ui_thread=GetCurrentThreadId();':
        '  host_probe_log("host_start",0);\n'
        '  const char *leading = getenv("EXR_TYPOGRAPHY_LINE_HEIGHT");\n'
        '  if (leading) typography_line_height = (float)atof(leading);\n'
        '  if (typography_line_height < 1.59f || typography_line_height > 1.91f) return 2;\n'
        '  host_probe_ui_thread=GetCurrentThreadId();',
        '    exr_status status = path ? exr_font_open(path, &g.font, &error) : EXR_MEMORY;':
        '    double font_started = host_probe_ms();\n'
        '    exr_status status = path ? exr_font_open(path, &g.font, &error) : EXR_MEMORY;\n'
        '    host_probe_log("font_load_ms",host_probe_ms()-font_started);',
    }
    for before, after in edits.items():
        assert source.count(before) == 1, before
        source = source.replace(before, after)
    generated = args.work / 'reader-measured.c'
    generated.write_text(source, encoding='utf-8')
    flags = ['-O2', '-I', ROOT/'include', '-I', ROOT/'examples', '-I', ROOT/'examples/windows',
             '-I', ROOT/'tools/perf']
    commands = [
        ['gcc', *flags, '-DEXR_READER_WINDOWS_SHELL=1', '-c', generated, '-o', args.work/'reader.o'],
        ['g++', *flags, '-std=c++17', '-c', ROOT/'examples/windows/shell_d2d.cpp', '-o', args.work/'d2d.o'],
        ['g++', *flags, '-std=c++17', '-c', ROOT/'examples/windows/shell_epub.cpp', '-o', args.work/'epub.o'],
        ['g++', args.work/'reader.o', args.work/'d2d.o', args.work/'epub.o', '-o', args.work/'TypographyBench.exe',
         '-L'+str(args.sdk_build), '-lexreader', args.sdk_build/'_deps/expat-build/libexpat.a',
         args.sdk_build/'_deps/miniz-build/libminiz.a', '-ld2d1', '-ldwrite', '-lgdi32', '-lcomdlg32', '-lcomctl32',
         '-lshell32', '-lole32', '-loleaut32', '-luuid', '-luiautomationcore', '-lpsapi', '-lm'],
    ]
    for command in commands:
        print(' '.join(map(str, command)), flush=True)
        execute(command)
    shutil.copy2(args.sdk_build/'libexreader.dll', args.work/'libexreader.dll')
    files = ['examples/reader.c', 'examples/windows/shell_d2d.cpp', 'examples/windows/shell_epub.cpp',
             'tools/perf/typography_probe.inc']
    write_json(args.work/'build.json', dict(
        source_revision=execute(['git', 'rev-parse', 'HEAD'], cwd=ROOT).strip(),
        commands=[[str(x) for x in c] for c in commands], compiler=execute(['gcc', '--version']).splitlines()[0],
        input_files={f: sha(ROOT/f) for f in files}, generated_host=identity(generated),
        exe=identity(args.work/'TypographyBench.exe'), dll=identity(args.work/'libexreader.dll'),
        sdk_build=str(args.sdk_build), instrumentation_replacements=edits))


def trace(path):
    return [(r[0], float(r[1]), float(r[2])) for r in csv.reader(path.open())]


def percentile(values, fraction):
    return sorted(values)[math.ceil(fraction*len(values))-1]


def metrics(rows):
    def event(name):
        return next(r for r in rows if r[0] == name)
    begin, end = event('keys_begin')[1], event('keys_end')[1]
    keys = [r for r in rows if begin < r[1] < end]
    inputs = [r for r in keys if r[0] == 'input_gen']
    assert len(inputs) == 20
    latencies = []
    for index, inp in enumerate(inputs):
        bound = inputs[index+1][1] if index+1 < len(inputs) else end
        present = next(r for r in keys if r[0] == 'present_gen' and inp[1] < r[1] < bound and r[2] != inp[2])
        latencies.append(present[1]-inp[1])
    opened = event('book_open_begin')[1]
    first = next(r for r in rows if r[0] == 'present_gen' and r[1] > opened and r[2] > 0)
    render = next(r for r in rows if r[0] == 'render_ms' and r[1] > opened)
    rasters = [r[2] for r in keys if r[0]=='render_ms']
    font_ms = event('font_load_ms')[2]
    return dict(open_including_font_ms=font_ms+first[1]-opened, font_load_ms=font_ms,
                book_open_to_present_ms=first[1]-opened, startup_to_first_present_ms=first[1]-event('host_start')[1],
                first_screen_render_ms=render[2], page_turn_p50_ms=percentile(latencies, .50),
                page_turn_p95_ms=percentile(latencies, .95), page_turn_max_ms=max(latencies),
                turn_raster_p95_ms=percentile(rasters,.95) if rasters else 0,
                peak_working_set_mib=event('peak_working_set_bytes')[2]/1048576,
                peak_commit_mib=event('peak_commit_bytes')[2]/1048576,
                total_pages=int(event('total_pages')[2]), count_ms=event('count_ms')[2],
                page_turn_samples=20, cache_hits=sum(r[0]=='cache_hit' for r in keys)), latencies


def launch(args, profile, script, folder, font, height, capture=False):
    folder.mkdir(parents=True, exist_ok=True)
    drive = folder/'steps.drive'
    drive.write_text('\n'.join(script)+'\n', encoding='utf-8')
    paint = folder/'paint.csv'
    assert not paint.exists(), paint
    environment = dict(os.environ, EXR_PAINT_TRACE=str(paint), EXR_TYPOGRAPHY_LINE_HEIGHT=str(height))
    environment.pop('EXR_PAINT_REPEAT', None)
    environment.pop('EXR_PAINT_MARKER', None)
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    command = [str(args.work/'TypographyBench.exe'), '--offscreen', '--data', str(profile),
               '--font', str(font), '--drive', str(drive), '--evidence', str(folder)]
    foreground = C.windll.user32.GetForegroundWindow
    foreground.restype = C.c_void_p
    before = foreground()
    cpu_before = system_times()
    started = datetime.now(timezone.utc).isoformat()
    process = subprocess.Popen(command, env=environment, startupinfo=startup, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    captured = False
    try:
        deadline = time.monotonic()+240
        while process.poll() is None:
            if time.monotonic() > deadline:
                raise TimeoutError(str(folder))
            if capture and not captured and paint.exists() and 'capture_ready,' in paint.read_text():
                result = execute([sys.executable, '-X', 'utf8', args.capture, process.pid, folder/'window.png'])
                write_json(folder/'capture.json', json.loads(result))
                captured = True
            time.sleep(.05)
        assert process.returncode == 0, (folder, process.returncode)
        assert not capture or captured
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    after = foreground()
    cpu_after = system_times()
    idle, kernel, user = [b-a for a,b in zip(cpu_before,cpu_after)]
    write_json(folder/'process.json', dict(command=command, exit_code=process.returncode,
               capture=captured, foreground_before=before, foreground_after=after,
               foreground_unchanged=before==after, started_utc=started,
               ended_utc=datetime.now(timezone.utc).isoformat(),
               system_cpu_busy_pct=100*(1-idle/(kernel+user))))
    log = folder/'drive.log'
    assert all(line.split('\t')[3]=='PASS' for line in log.read_text(encoding='utf-8').splitlines()
               if line.startswith('STEP\t')), log
    # Host drive logs can contain short book previews; retain only pass/fail steps.
    (folder/'drive.txt').write_text('\n'.join(line for line in log.read_text(encoding='utf-8').splitlines()
                                            if line.startswith(('HOST\t','STEP\t')))+'\n', encoding='utf-8')
    log.unlink()


def run(args):
    args.output.mkdir(parents=True, exist_ok=True)
    build_info = json.loads((args.work/'build.json').read_text(encoding='utf-8'))
    assert sha(args.work/'TypographyBench.exe') == build_info['exe']['sha256']
    assert sha(args.work/'libexreader.dll') == build_info['dll']['sha256']
    write_json(args.output/'protocol.json', dict(created_utc=datetime.now(timezone.utc).isoformat(),
        build=build_info, fonts={k: identity(v) for k,v in FONTS.items()}, book=identity(BOOK),
        capture=identity(args.capture), collector=identity(__file__), font_px=18, typography_dpi=96, repeats=3, turns_per_repeat=20,
        percentiles='nearest rank: sorted[ceil(q*n)-1]', dispersion='100*(max-min)/median, per metric',
        unacceptable_p95_ms=100, severe_p95_ms=200, seed=20261107,
        cache='new process and clean copied seed library each run; OS file cache is warm/uncontrolled',
        memory='Windows process peak working set / peak commit through end of 20 turns, before page counting',
        open='font_load_ms + book_open_begin to first nonzero present_gen; library import excluded',
        first_screen='first render_ms after book_open_begin; startup and full book open also retained'))
    seed = args.work/'seed-profile'
    if not (seed/'library.sqlite').exists():
        launch(args, seed, ['delay|0', 'import|'+str(BOOK), 'wait_idle', 'quit'],
               args.work/'seed-evidence', FONTS['sans'], 1.75)
    configs = list(itertools.product(FONTS, LINE_HEIGHTS, VIEWPORTS))
    results = []
    for repeat in range(1,4):
        order = configs.copy()
        random.Random(20261107+repeat).shuffle(order)
        for font, height, (width, view_height) in order:
            key = f'{font}-lh{height:.2f}-{width}x{view_height}-r{repeat}'
            folder = args.output/'raw'/key
            if (folder/'result.json').exists():
                results.append(json.loads((folder/'result.json').read_text(encoding='utf-8')))
                continue
            profile = args.work/'profiles'/key
            assert not profile.exists(), profile
            profile.mkdir(parents=True)
            shutil.copy2(seed/'library.sqlite', profile/'library.sqlite')
            script = ['delay|0', 'wait_idle', 'shell|on', 'shell_dpi|96', 'shell_font|18',
                      f'shell_client|{width}|{view_height}', 'wait_idle', 'probe_mark|book_open_begin',
                      'open|紅樓夢', 'wait_idle', 'probe_wait|500', 'probe_mark|keys_begin']
            for _ in range(20):
                script += ['probe_key', 'probe_wait|400', 'wait_idle']
            script += ['probe_mark|keys_end', 'typography_count', 'shell_measure|layout',
                       'probe_mark|capture_ready', 'probe_wait|10000' if repeat==1 else 'probe_wait|0', 'quit']
            print('RUN', key, flush=True)
            launch(args, profile, script, folder, FONTS[font], height, capture=repeat==1)
            layout = json.loads((folder/'layout.json').read_text(encoding='utf-8'))
            assert layout['client']==[width, view_height] and layout['dpi']==96
            assert layout['font']==18 and abs(layout['line_height']-height)<.00001
            # Retain geometry and glyph positions, never book text.
            layout.pop('text', None)
            write_json(folder/'layout.json', layout)
            m, samples = metrics(trace(folder/'paint.csv'))
            record = dict(run=key, repeat=repeat, font=font, line_height=height, client_width=width,
                          client_height=view_height, body_width=layout['page'][0], body_height=layout['page'][1], **m)
            write_json(folder/'result.json', record)
            with (folder/'turns.csv').open('w', newline='', encoding='utf-8') as f:
                writer=csv.writer(f); writer.writerow(['turn','input_to_present_ms'])
                writer.writerows(enumerate(samples,1))
            results.append(record)
            print(json.dumps(record), flush=True)
    summarize(args)


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as f:
        writer=csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def summarize(args):
    records = [json.loads(p.read_text(encoding='utf-8')) for p in sorted((args.output/'raw').glob('*/result.json'))]
    assert len(records)==54, len(records)
    write_csv(args.output/'runs.csv', records)
    summaries=[]
    measured=['open_including_font_ms','font_load_ms','first_screen_render_ms','page_turn_p50_ms',
              'page_turn_p95_ms','turn_raster_p95_ms','peak_working_set_mib','peak_commit_mib','total_pages']
    for font, height, (width, view_height) in itertools.product(FONTS, LINE_HEIGHTS, VIEWPORTS):
        group=[r for r in records if (r['font'],r['line_height'],r['client_width'],r['client_height'])==
               (font,height,width,view_height)]
        assert len(group)==3
        row=dict(font=font,line_height=height,client_width=width,client_height=view_height)
        for metric in measured:
            values=[r[metric] for r in group]
            median=statistics.median(values)
            row[metric]=median
            row[metric+'_range']=max(values)-min(values)
            row[metric+'_dispersion_pct']=100*(max(values)-min(values))/median if median else 0
        row['p95_over_10pct']=row['page_turn_p95_ms_dispersion_pct']>10
        row['metrics_over_10pct']=';'.join(m for m in measured if row[m+'_dispersion_pct']>10)
        row['unacceptable']=row['page_turn_p95_ms']>100
        summaries.append(row)
    write_csv(args.output/'summary.csv', summaries)
    assert all(r['total_pages_range']==0 for r in summaries)
    assert sum(r['page_turn_samples'] for r in records)==1080
    print(json.dumps(summaries,ensure_ascii=False,indent=2))


def selfcheck():
    assert percentile(list(range(1,21)),.5)==10
    assert percentile(list(range(1,21)),.95)==19
    # A stale generation must not satisfy an input; the next input bounds matching.
    rows=[('host_start',0,0),('font_load_ms',1,2),('book_open_begin',2,0),
          ('render_ms',3,1),('present_gen',4,1),('keys_begin',5,0)]
    for i in range(20):
        rows += [('input_gen',10+i*10,i+1),('present_gen',11+i*10,i+1),('present_gen',13+i*10,i+2)]
    rows += [('keys_end',220,0),('peak_working_set_bytes',221,1048576),
             ('peak_commit_bytes',221,2097152),('total_pages',222,100),('count_ms',222,1)]
    result, samples=metrics(rows)
    assert samples==[3]*20 and result['open_including_font_ms']==4
    print('selfcheck PASS')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build','run','summarize','selfcheck'])
    parser.add_argument('--work', type=Path)
    parser.add_argument('--sdk-build', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--capture', type=Path)
    args=parser.parse_args()
    for name in ('work','sdk_build','output','capture'):
        value=getattr(args,name)
        if value is not None: setattr(args,name,value.resolve())
    if args.command=='selfcheck': selfcheck()
    else: globals()[args.command](args)
