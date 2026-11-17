"""Reproduce serial benchmarks after building; never overlap with builds/tests."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
BENCH='evidence/pdf-deck-decode-20261117/bench_engine.py'
def bench(name,library,fixture,pages,widths,skip=None):
    output=Path(f'out/deck-decode/{name}/bench.json')
    if output.exists():
        report=json.loads(output.read_text())
        if report['idle_cpu_percent']<0:
            raise SystemExit(f'Reject contended measurement: {output}')
        digest=hashlib.sha256(Path(library).read_bytes()).hexdigest()
        for summary in output.parent.glob('.repeat-*/*/summary.json'):
            if json.loads(summary.read_text())['library_sha256']!=digest:
                raise SystemExit(f'Reject stale library capture: {summary}')
        return
    env=os.environ.copy()
    if skip is not None: env['EXR_PDF_DIAGNOSTIC_SKIP']=skip
    print(name,repr(skip),flush=True)
    if skip is None:
        env.pop('EXR_PDF_DIAGNOSTIC_SKIP',None)
        if b'EXR_PDF_DIAGNOSTIC_SKIP' in Path(library).read_bytes():
            raise SystemExit(f'Rebuild production library without diagnostics: {library}')
    subprocess.run([sys.executable,'-X','utf8',BENCH,'--library',library,'--input',fixture,'--expect-pages',str(pages),'--widths',*map(str,widths),'--runs','12','--repeat','2','--idle-threshold','15','--repo','.','--out',str(output)],env=env,check=True)
    report=json.loads(output.read_text())
    if report['idle_cpu_percent']<0:
        raise SystemExit(f'Reject contended measurement: {output}')
deck='tests/fixtures/pdf-ppt/deck.pdf'
pptx='tests/fixtures/pdf-hybrid-real/pptx-20.pdf'
if '--final-only' not in sys.argv:
    for name,skip in [('no-images-text','it'),('no-images-paths','ip'),('no-images-text-paths','itp'),('no-images-clips','ic'),('interpreter-only','itpc'),('no-interpreter','s')]:
        bench('ablations/'+name,'out/deck-decode/cache-only/libexreader.dll',deck,15,[1200],skip)
bench('production-final-v5-deck','build/perf/libexreader.dll',deck,15,[600,1200])
bench('production-final-v5-pptx','build/perf/libexreader.dll',pptx,20,[600,1200,2400])
bench('production-baseline-deck','out/deck-decode/before/libexreader.dll',deck,15,[600,1200])
bench('production-baseline-pptx','out/deck-decode/before/libexreader.dll',pptx,20,[600,1200,2400])
for name,skip in [('cache-only',''),('no-images','i')]:
    bench('ablations-resumed/'+name,'out/deck-decode/cache-only/libexreader.dll',deck,15,[1200],skip)
subprocess.run([sys.executable,'-X','utf8','tools/probe_pdf_open.py','--baseline','out/deck-decode/before/libexreader.dll','--candidate','build/perf/libexreader.dll','--input',deck,pptx,'--samples','1000','--out','out/deck-decode/open-probe.json'],check=True)
