"""Independent live HWND focus contrast; no edits or monkeypatches of F3 judge."""
import argparse, ctypes, hashlib, json, os, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/reader_windows_preferences'))
import check_ui as F
import uiautomation as auto
assert os.name=='nt' and os.environ.get('GITHUB_ACTIONS')=='true'
p=argparse.ArgumentParser()
for name in ('candidate','font','fixtures','output'):p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True)
app=F.App(a.candidate.resolve(),a.font.resolve(),out/'profile')
observations=[]
try:
    app.wait_idle();app.settle();app.import_file(a.fixtures.resolve()/'Reading sample.txt');app.open('Reading sample');app.wait_idle()
    # Reproduce original failed client geometry and exact explicit-light interaction.
    app.fit_page((797,541));app.open_dialog()
    for field,value in ((F.FONT,'24'),(F.LINE,'1.60'),(F.PARAGRAPH,'12'),(F.MARGIN,'48')):F.set_text(app.field(field),value)
    app.choose(F.THEME,0);app.apply();app.close_dialog()
    page=app.control('page')
    def capture(label):
        time.sleep(.3)
        image=app.page_shot(label+'.bmp',out)
        dx,dy,w,h=F.layout(F.page_client(app),(720,1040))
        row=dict(label=label,client=F.page_client(app),layout=[dx,dy,w,h],ui_state=F.send(page,0x129),focused=F.A.focus_of(app.process.pid)==page,surround=F.at(image,max(dx-4,1),max(dy-4,1)),corner=F.at(image,dx+6,dy+6),edge_dark=sum(sum(F.at(image,x,1))<260 for x in range(2,image[0]-2)),boundary_edge=[F.at(image,x,0) for x in range(2,image[0]-2)],interior_sha256=hashlib.sha256(bytes(c for y in range(dy+3,dy+h-3) for x in range(dx+3,dx+w-3) for c in F.at(image,x,y))).hexdigest())
        observations.append(row);print(json.dumps(row),flush=True)
    capture('light-dialog-closed')
    # UI Automation moves real focus; independently verify the owning thread.
    auto.ControlFromHandle(app.control('import')).SetFocus()
    app.wait(lambda: F.A.focus_of(app.process.pid)==app.control('import'))
    capture('focus-away')
    auto.ControlFromHandle(page).SetFocus()
    app.wait(lambda: F.A.focus_of(app.process.pid)==page)
    capture('focus-restored')
    # Native UI cue policy: request hide, then show, at the parent and observe child propagation.
    F.send(app.window,0x127,1|(1<<16),0);capture('hide-focus-cue')
    F.send(app.window,0x127,2|(1<<16),0);capture('show-focus-cue')
    # Real keyboard Tab navigation must reveal a visible cue on return to page.
    F.send(app.window,0x127,1|(1<<16),0)
    auto.ControlFromHandle(app.control('import')).SetFocus()
    app.focus()
    for _ in range(80):
        F.A.tap(F.A.VK_TAB)
        if F.A.focus_of(app.process.pid)==page: break
    assert F.A.focus_of(app.process.pid)==page, 'keyboard could not reach page'
    capture('keyboard-tab-page')
    # Dark canvas: the control-boundary cue remains visible without touching text.
    app.open_dialog();app.choose(F.THEME,1);app.apply();app.close_dialog()
    auto.ControlFromHandle(page).SetFocus()
    F.send(app.window,0x127,1|(1<<16),0);capture('dark-hide-focus-cue')
    F.send(app.window,0x127,2|(1<<16),0);capture('dark-show-focus-cue')
finally:
    app.close_app()
    (out/'observations.json').write_text(json.dumps(dict(source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],observations=observations),indent=2))
