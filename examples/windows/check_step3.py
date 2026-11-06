# SPDX-License-Identifier: MIT
"""Offscreen Windows acceptance runner. Never activates or sends global input.
Run: python examples/windows/check_step3.py EXE FONT OUTPUT [--smoke]
"""
import ctypes as c
import ctypes.wintypes as w
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
USER = c.WinDLL('user32', use_last_error=True)
USER.GetForegroundWindow.restype = w.HWND
USER.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]


def run(exe, font, out, script, data=None, phase='0'):
    out.mkdir(parents=True, exist_ok=True)
    script_file = out / 'run.drive'
    script_file.write_text('\n'.join(script) + '\n', encoding='utf-8')
    started = time.monotonic()
    process = subprocess.Popen([str(exe), '--offscreen', '--font', str(font), '--drive', str(script_file),
                                '--data', str(data or out / 'profile'), '--evidence', str(out), '--phase', phase],
                               creationflags=subprocess.CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    foreground = 0
    try:
        while process.poll() is None:
            owner = w.DWORD()
            USER.GetWindowThreadProcessId(USER.GetForegroundWindow(), c.byref(owner))
            if owner.value == process.pid:
                foreground += 1
                raise RuntimeError('offscreen process became foreground')
            if time.monotonic() - started > 240:
                raise TimeoutError(str(out))
            time.sleep(.05)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait()
    (out / 'process.json').write_text(json.dumps({'exit': process.returncode, 'foreground_observations': foreground,
                                                 'elapsed': time.monotonic()-started}), encoding='utf-8')
    failures = [line for line in (out/'drive.log').read_text(encoding='utf-8').splitlines() if line.startswith('STEP\t') and '\tFAIL\t' in line]
    print(out.name, 'exit', process.returncode, 'failures', json.dumps(failures,ensure_ascii=True), flush=True)
    return failures


def make_books(folder):
    folder.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('fixtures', ROOT / 'tests/windows_host/make_fixtures.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rng = random.Random(20261105)
    pool = '天地玄黄宇宙洪荒日月盈昃辰宿列张寒来暑往秋收冬藏云腾致雨露结为霜金生丽水玉出昆冈剑号巨阙珠称夜光果珍李柰菜重芥姜海咸河淡鳞潜羽翔龙师火帝鸟官人皇始制文字乃服衣裳推位让国有虞陶唐爱育黎首臣伏戎羌遐迩一体率宾归王鸣凤在竹白驹食场化被草木赖及万方'
    text = ''.join(rng.choice(pool) for _ in range(100000))
    for name, vertical in [('horizontal', False), ('vertical', True)]:
        path = folder / (name + '.epub')
        module.epub(path, name, text)
        if vertical:
            with zipfile.ZipFile(path) as z:
                entries = {n: z.read(n) for n in z.namelist()}
            entries['OPS/c0.xhtml'] = entries['OPS/c0.xhtml'].replace(b'<head>', b'<head><style>html{writing-mode:vertical-rl}</style>')
            with zipfile.ZipFile(path, 'w') as z:
                for name_, value in entries.items():
                    info = zipfile.ZipInfo(name_, date_time=(2026,1,1,0,0,0))
                    info.compress_type = zipfile.ZIP_STORED if name_=='mimetype' else zipfile.ZIP_DEFLATED
                    z.writestr(info, value)
    (folder/'inputs.json').write_text(json.dumps({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob('*.epub')}, indent=2))


def client_image(path):
    from PIL import Image
    rect = json.loads(path.with_suffix('.client.json').read_text())
    x,y,w,h = rect
    with Image.open(path) as image:
        return image.convert('RGBA').crop((x,y,x+w,y+h))


def diff_pixels(a,b):
    if a.size != b.size:
        return -1
    left,right=a.tobytes(),b.tobytes()
    return sum(left[i:i+4] != right[i:i+4] for i in range(0,len(left),4))


def phases(baseline, off, on, font, sample, out):
    import shutil
    out.mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,str(ROOT/'tests/windows_host/make_fixtures.py'),'--output',str(out/'fixtures')],check=True)
    stable = out/'stable'; stable.mkdir(exist_ok=True)
    data = out/'profile'
    results = {}
    for label, exe in [('off1',baseline),('off2',baseline),('step3-off',off),('step3-on-legacy',on)]:
        shutil.copy2(exe,stable/'EXReader.exe')
        shutil.copy2(exe.parent/'exreader.dll',stable/'exreader.dll')
        results[label] = {}
        for index,phase in enumerate('abc',1):
            steps = (ROOT/f'tests/windows_host/phase-{phase}.txt').read_text(encoding='utf-8')
            steps = steps.replace('@@SAMPLE@@',str(sample)).replace('@@FIXTURES@@',str(out/'fixtures')).splitlines()
            results[label][phase] = run(stable/'EXReader.exe',font,out/label/phase,steps,data,str(index))
        assert data.resolve().parent == out.resolve()
        data.rename(out/('profile-'+label))
    reference = sorted((out/'off1').glob('*/*.png'))
    assert len(reference)==8,reference
    comparisons={}
    for group in ['off2','step3-off','step3-on-legacy']:
        comparisons[group]={str(p.relative_to(out/'off1')):diff_pixels(client_image(p),client_image(out/group/p.relative_to(out/'off1'))) for p in reference}
    image=client_image(reference[0]); negative=image.copy()
    pixel=negative.getpixel((20,20));negative.putpixel((20,20),((pixel[0]+1)%256,*pixel[1:]))
    from PIL import Image
    outer=Image.open(reference[0]).convert('RGBA'); changed=outer.copy()
    pixel=changed.getpixel((0,0)); changed.putpixel((0,0),((pixel[0]+1)%256,*pixel[1:]))
    x,y,w,h=json.loads(reference[0].with_suffix('.client.json').read_text())
    negatives={'client_rgb_one':diff_pixels(image,negative),'nonclient_one':diff_pixels(image,changed.crop((x,y,x+w,y+h)))}
    assert negatives=={'client_rgb_one':1,'nonclient_one':0}
    bad=outer.copy();pixel=bad.getpixel((x+20,y+20));bad.putpixel((x+20,y+20),((pixel[0]+1)%256,*pixel[1:]))
    for name,picture,expected in [('negative-client',bad,1),('negative-nonclient',changed,0)]:
        file=out/(name+'.png');picture.save(file)
        file.with_suffix('.client.json').write_text(json.dumps([x,y,w,h]))
        result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--compare',str(reference[0]),str(file)],check=False)
        assert result.returncode==expected

    report={'phases':results,'client_diffpx':comparisons,'negative':negatives}
    (out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(comparisons,indent=2),flush=True)
    assert all(all(count==0 for count in group.values()) for group in comparisons.values())


def stress(exe,font,out):
    make_books(out/'books')
    reports={}
    for direction in ['horizontal','vertical']:
        steps=[f'import|{out/"books"/(direction+".epub")}',f'open|{direction}','shell|on','shell_dpi|96',
               'shell_font|18','shell_client|1280|800','wait_idle']
        steps += ['next','wait_idle']*7
        steps += ['shell_measure|before','shell_client|1000|800','shell_measure|cap',
                  'shell_client|720|560','shell_measure|small','shell_client|1280|800','shell_measure|roundtrip',
                  'shell_font|18','shell_measure|same','delay|700', 'resize|1000|700','probe_wait|250',
                  'resize|1150|750','resize|1280|850','probe_wait|180','wait_idle','delay|0','shell_measure|busy',
                  'shell_client|1280|800','shell_measure|busy-roundtrip','shell_dpi|120','shell_measure|dpi120',
                  'shell_dpi|144','shell_measure|dpi144','shell_dpi|96','shell_client|1280|800','shell_measure|dpi-roundtrip',
                  'shell|off','wait_idle','check|legacy_ids','shell_measure|legacy',
                  'shell|on','wait_idle','shell_measure|shell-again','quit']
        dest=out/direction
        assert not run(exe,font,dest,steps)
        m={p.stem:json.loads(p.read_text(encoding='utf-8')) for p in dest.glob('*.json') if p.name!='process.json'}
        for name in ['roundtrip','busy-roundtrip','dpi-roundtrip','shell-again']:
            assert m[name]['range']==m['before']['range'],(direction,name,m[name]['range'],m['before']['range'])
            assert m[name]['text']==m['before']['text'],(direction,name)
        assert m['cap']['builds']==m['before']['builds']
        assert m['same']['builds']==m['roundtrip']['builds']
        assert m['dpi144']['builds']-m['dpi120']['builds']==1
        assert m['busy']['epoch']==m['busy']['frame_epoch']
        assert m['legacy']['page']==[720,1040] and m['legacy']['font']==42
        reports[direction]={name:{k:d[k] for k in ['client','page','font','range','epoch','frame_epoch','builds']} for name,d in m.items()}
    (out/'results.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')


def matrix(exe,font,out):
    make_books(out/'books')
    steps=[f'import|{out/"books/horizontal.epub"}','open|horizontal','shell|on','shell_dpi|96']
    for width in [1280,1000,999,720]:
        for font_size in [14,17,18,24,32]:
            steps += [f'shell_font|{font_size}',f'shell_client|{width}|800','wait_idle','chapter_home','wait_idle']
            for page in range(20):
                steps += [f'shell_measure|{width}-{font_size}-{page:02}','next','wait_idle']
    steps += ['quit']
    assert not run(exe,font,out/'horizontal',steps)
    assert len(list((out/'horizontal').glob('[0-9]*.json')))==400
    for path in (out/'horizontal').glob('*.json'):
        if path.name=='process.json':continue
        data=json.loads(path.read_text(encoding='utf-8'))
        assert data['scale']==1 and data['display']==data['page']
        assert data['target_dpi']==[96]*4
        assert data['epoch']==data['frame_epoch']


def selection(exe,font,out):
    make_books(out/'books')
    for direction in ['horizontal','vertical']:
        # At 96 dpi, 1280x800, font 18: page origin (334,32/48) in page-child coordinates.
        start,end=((338,42),(496,71)) if direction=='horizontal' else ((925,52),(896,228))
        steps=[f'import|{out/"books"/(direction+".epub")}',f'open|{direction}','shell|on','shell_dpi|96',
               'shell_font|18','shell_client|1280|800','drag|0|0|20|20','wait_idle','state|outside',
               f'drag|{start[0]}|{start[1]}|{end[0]}|{end[1]}','wait_idle','check|selection|nonempty',
               'copy','check|clipboard|contains|归唐率','state|selected','add_note|physical-selection','wait_idle','next','wait_idle','jump_note|0',
               'wait_idle','check|selection|nonempty','state|note-restored','quit']
        dest=out/direction
        assert not run(exe,font,dest,steps)
        states={}
        for line in (dest/'drive.log').read_text(encoding='utf-8').splitlines():
            fields=line.split('\t')
            if fields[0]=='STATE':states[fields[2]]=dict(part.split('=',1) for part in fields[4].split(';') if '=' in part)
        assert states['outside']['selection_active']=='0'
        assert states['selected']['selection_start']==states['note-restored']['selection_start']
        assert states['selected']['selection_end']==states['note-restored']['selection_end']


def main():
    if sys.argv[1]=='--compare':
        count=diff_pixels(client_image(Path(sys.argv[2])),client_image(Path(sys.argv[3])))
        print('client_diffpx='+str(count))
        raise SystemExit(0 if count==0 else 1)
    if sys.argv[1] in ['--matrix','--selection']:
        (matrix if sys.argv[1]=='--matrix' else selection)(*[Path(arg).resolve() for arg in sys.argv[2:5]])
        return
    if sys.argv[1]=='--stress':
        stress(*[Path(arg).resolve() for arg in sys.argv[2:5]])
        return
    if sys.argv[1]=='--phases':
        phases(*[Path(arg).resolve() for arg in sys.argv[2:8]])
        return
    exe, font, out = [Path(arg).resolve() for arg in sys.argv[1:4]]
    make_books(out/'books')
    for direction in ['horizontal','vertical']:
        steps = [f'import|{out / "books" / (direction + ".epub")}', f'open|{direction}', 'shell|on', 'wait_idle',
                 'shell_font|18', 'shell_client|1280|800', 'wait_idle', 'shell_measure|initial', 'snapshot|initial']
        if '--smoke' not in sys.argv:
            for label, width, height, dpi in [('1280',1280,800,96),('2560',2560,1440,96),('125',1920,1080,120),('150',2560,1440,144)]:
                steps += [f'shell_dpi|{dpi}', f'shell_client|{width}|{height}', 'wait_idle']
                for i in range(20):
                    steps += [f'shell_measure|{label}-{i:02}', 'next', 'wait_idle']
                steps += [f'snapshot|{label}']
        steps += ['quit']
        assert not run(exe,font,out/direction,steps)

if __name__=='__main__':
    main()
