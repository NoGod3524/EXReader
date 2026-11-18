"""Reproduce acceptance with the freshly linked committed candidate; run serially."""
from pathlib import Path
import hashlib,json,struct,subprocess,sys,time
import psutil
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent/'continuation'
OUT.mkdir(parents=True,exist_ok=True)
A=ROOT.parent/'resample-dlls/main-653e44b.dll'
B=ROOT/'build/perf/libexreader.dll'
def sections(path):
    data=path.read_bytes()
    pe=struct.unpack_from('<I',data,0x3c)[0]
    count=struct.unpack_from('<H',data,pe+6)[0]
    table=pe+24+struct.unpack_from('<H',data,pe+20)[0]
    result={}
    for i in range(count):
        pos=table+40*i
        name=data[pos:pos+8].rstrip(b'\0').decode()
        size,offset=struct.unpack_from('<II',data,pos+16)
        result[name]=hashlib.sha256(data[offset:offset+size]).hexdigest()
    return {'sha256':hashlib.sha256(data).hexdigest(),'sections':result}
(OUT/'build-identity.json').write_text(json.dumps({
    'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
    'baseline':sections(A),'committed_candidate':sections(ROOT.parent/'resample-dlls/final.dll'),
    'relinked_candidate':sections(B)},indent=2))
def foreign():
    allowed={p.pid for p in psutil.Process().parents()+psutil.Process().children(recursive=True)}|{psutil.Process().pid}
    return [p.pid for p in psutil.process_iter(['name']) if p.pid not in allowed and
            p.info['name'].lower().startswith(('python','gcc','cc1','ninja','cmake','ctest','exreader-'))]
def run(*args):
    if str(args[0]).endswith('gated_pairs.py'):
        output=Path(args[args.index('--out')+1])
        previous=json.loads(output.read_text()) if output.exists() else None
        pdf=Path(args[args.index('--input')+1])
        if (previous and previous['library_b_sha256']==sections(B)['sha256'] and
            previous['library_a_sha256']==sections(A)['sha256'] and
            previous['input_sha256']==hashlib.sha256(pdf.read_bytes()).hexdigest() and
            previous['runs']==int(args[args.index('--runs')+1]) and
            previous['repeat']==int(args[args.index('--repeat')+1])):
            print('Reusing accepted paired capture:',output.name,flush=True)
            return
    # This runner rejects overlapping timed sweeps itself, retaining accepted
    # sweeps across idle waits. A foreign job during a wait is not a bad sample.
    if str(args[0]).endswith('interleaved_ab.py'):
        output=Path(args[-1])
        previous=json.loads(output.read_text()) if output.exists() else None
        if (previous and previous['library_b_sha256']==sections(B)['sha256'] and
            previous['library_a_sha256']==sections(A)['sha256'] and
            previous['pdf_sha256']==hashlib.sha256(Path(args[3]).read_bytes()).hexdigest() and
            previous['reps']==int(args[7]) and previous['width']==int(args[4]) and
            previous['pages']==[int(args[5]),int(args[6])]):
            print('Reusing accepted same-process capture:',output.name,flush=True)
            return
        subprocess.run([sys.executable,'-X','utf8',*map(str,args)],cwd=ROOT,check=True)
        return
    while True:
        while foreign():
            print('Waiting for other measurement/build processes',flush=True)
            time.sleep(10)
        process=subprocess.Popen([sys.executable,'-X','utf8',*map(str,args)],cwd=ROOT)
        overlap=False
        while process.poll() is None:
            overlap=bool(foreign()) or overlap
            time.sleep(.5)
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode,args)
        if not overlap:
            return
        print('Rejected capture overlapping another process; retrying',flush=True)
for name,pdf,width,reps in [
 ('image-heavy','pdf-large/image-heavy-100',1200,7),
 ('vector-heavy','pdf-large/vector-heavy-100',1200,9),
 ('real-mixed','pdf-large/real-mixed-120',1200,7),
 ('pptx-600','pdf-hybrid-real/pptx-20',600,41),
 ('pptx-1200','pdf-hybrid-real/pptx-20',1200,41),
 ('deck','pdf-ppt/deck',1200,31),
 ('word-5','pdf-hybrid-real/word-5',1200,41)]:
    count=120 if name=='real-mixed' else 100 if name in ('image-heavy','vector-heavy') else 20 if name.startswith('pptx') else 15 if name=='deck' else 5
    run('evidence/resample-path-20261118/interleaved_ab.py',A,B,f'tests/fixtures/{pdf}.pdf',width,1,count,reps,OUT/f'interleaved-{name}.json')
for name in ['image-heavy-100','real-mixed-120','vector-heavy-100']:
    run('evidence/resample-path-20261118/gated_pairs.py','--library-a',A,'--library-b',B,'--input',f'tests/fixtures/pdf-large/{name}.pdf','--runs',5,'--repeat',4,'--out',OUT/f'paired-{name}.json','--idle-timeout',60)
for name,pdf,widths in [('pptx-20','pdf-hybrid-real/pptx-20',[600,1200]),('deck','pdf-ppt/deck',[1200]),('word-5','pdf-hybrid-real/word-5',[1200])]:
    run('evidence/resample-path-20261118/gated_pairs.py','--library-a',A,'--library-b',B,'--input',f'tests/fixtures/{pdf}.pdf','--widths',*widths,'--runs',5,'--repeat',4,'--out',OUT/f'paired-{name}.json','--idle-timeout',60)
run('evidence/dense-vector-throughput-20261118/verify_pixels.py',A,B,OUT/'pixels.json')
with (OUT/'ctest.txt').open('w') as log:
    subprocess.run(['ctest','--test-dir','build/perf','--output-on-failure','-j','4'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
print('Acceptance captures complete',flush=True)
