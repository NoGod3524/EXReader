"""Real keyboard and AT-SPI delta audit; imports the existing client/driver."""
import argparse, hashlib, json, os, sys, time, traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/reader_a11y_gtk'))
import atspi_client as bus
from driver import Host, command, wait_until
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk, Gdk
from PIL import Image
TARGET='9fc407a5cce5a0bfe644a60bd8dc29f84dea6d0e'
SDK='edddc463c06ed5731195cdb8f06b2df6dff7699e'
LEAVES=('Search within book…','Directory / page entries…','Reading records…','Reading settings…','Larger text','Smaller text','Show or hide text and notes','Select page text','Add note from selection','Saved notes','Comment','Delete selected note','Book details…','Collections…','Account / Sync…','Import file…','Import folder…','Paste book files','Retry saving position','Cancel current operation','Zoom in','Zoom out')
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    assert os.environ['GITHUB_ACTIONS']=='true'
    p=argparse.ArgumentParser();p.add_argument('--payload',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--mode',choices=['OFF','ON'],required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    payload=a.payload.resolve();host=Host(payload/'bin/exreader-linux',payload/'Reader.otf',out)
    built=json.loads((payload.parent/'build.json').read_text())
    assert built['source_sha']==TARGET and built['sdk_version']=='3.41.0' and built['abi']==1 and built['files']['bin/exreader-linux']==digest(host.binary)
    report=dict(harness_sha=os.environ['GITHUB_SHA'],target_sha=TARGET,sdk_source=SDK,run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],compact=a.mode,program_sha256=digest(host.binary),font_sha256=digest(host.font),audit_completed=False,keyboard_accepted=False,contrast_accepted=False,screen_reader_accepted=False,checks=[],snapshots=[],findings=[],pending=['Orca and human speech/braille experience','Human verification of visible focus rings, clipping and overlap','Whole UI text/non-text contrast; measured pixel pairs do not establish foreground/background semantics','Physical desktop and compositor scaling beyond Xvfb'])
    settings=Gtk.Settings.get_default();screen=Gdk.Screen.get_default()
    probe=Gtk.Window();probe.realize()
    report['environment']=dict(gtk=[Gtk.MAJOR_VERSION,Gtk.MINOR_VERSION,Gtk.MICRO_VERSION],theme=settings.get_property('gtk-theme-name'),font=settings.get_property('gtk-font-name'),xft_dpi=settings.get_property('gtk-xft-dpi'),gdk_window_scale=probe.get_window().get_scale_factor(),screen_resolution=screen.get_resolution(),screen=[screen.get_width(),screen.get_height()],env={k:os.environ.get(k) for k in ('GTK_THEME','GDK_SCALE','GDK_DPI_SCALE','XDG_CONFIG_HOME')},xrdb=command('xrdb','-query').stdout,xdpyinfo=command('xdpyinfo').stdout)
    probe.destroy();app=None
    report['environment']['readback_source']='Same-environment GTK probe window and settings; actual host bounds, focus and name/role/state are separately obtained through AT-SPI. No in-process host DPI instrumentation.'
    def nodes(name=None,role=None):
        return [n for n in bus.walk(app) if (name is None or bus.name(n)==name) and (role is None or bus.role(n)==role) and bus.states(n).get('showing')]
    def focused(): return [dict(path=bus.path_of(n),name=bus.name(n),role=bus.role(n),states=bus.states(n)) for n in bus.focused_all(app)]
    def check(name,ok,actual,expected):
        row=dict(name=name,passed=bool(ok),actual=actual,expected=expected);report['checks'].append(row);print(json.dumps(row),flush=True)
        if not ok: report['findings'].append(dict(**row,target_sha=TARGET,reproduction='Run '+a.mode+' '+out.name+'; see keys.log and '+name+' snapshot',root_cause='Unconfirmed; inspect actual tree and keyboard trace',minimal_suggestion='Owner to inspect GTK focus/geometry handling; no production edits in D03'))
    def capture(name):
        tree=bus.dump(app);(out/(name+'.json')).write_text(json.dumps(tree,indent=2));host.screenshot(out/(name+'.png'),window='root')
        rects=[dict(path=bus.path_of(n),role=bus.role(n),name=bus.name(n),box=bus.extents(n),states=bus.states(n)) for n in bus.walk(app) if bus.states(n).get('showing')]
        with Image.open(out/(name+'.png')) as image: width,height=image.size
        outside=[r for r in rects if r['box'] and r['role'] in ('push button','toggle button','text','combo box','menu item') and (r['box']['x']<0 or r['box']['y']<0 or r['box']['x']+r['box']['width']>width or r['box']['y']+r['box']['height']>height)]
        report['snapshots'].append(dict(name=name,geometry=host.geometry(),focus=focused(),visible=rects,screen_pixels=[width,height],offscreen_candidates=outside,geometry_limit='Bounds only; text clipping, intentional scrolling and overlapping descendants require visual review',png_sha256=digest(out/(name+'.png')),tree_sha256=digest(out/(name+'.json'))))
    def wait_node(name,role): return wait_until(lambda:nodes(name,role),15,description=name)[0]
    def tab_to(name,role=None):
        for _ in range(80):
            if any(bus.name(n)==name and (role is None or bus.role(n)==role) for n in bus.focused_all(app)):return
            host.key('Tab')
        raise AssertionError('Keyboard Tab did not reach '+repr((name,role)))
    def phase(name,fn,requires_book=False):
        if requires_book and not host.host_state().get('book',0):
            report['findings'].append(dict(name=name,error='Prerequisite import/open did not complete',classification='blocked_by_import_not_product_failure',target_sha=TARGET,reproduction='Inspect import-open-failed PNG/tree and chooser key trace before evaluating this phase'))
            check(name+'-completed',False,'unevaluated: no open book','Successful real import prerequisite')
            return
        try:fn();capture(name)
        except Exception as exc:
            report['findings'].append(dict(name=name,error=repr(exc),traceback=traceback.format_exc(),target_sha=TARGET,reproduction='Keys in keys.log; phase '+name,root_cause='Unconfirmed host or harness failure',minimal_suggestion='Inspect failure PNG, tree, and exact key trace before owner fix'))
            check(name+'-completed',False,repr(exc),'phase completed')
            try:capture(name+'-failed');host.key('Escape','Escape');host.activate(host.window)
            except Exception:pass
    def choose_file(path,label):
        # Same real-keyboard chooser route as original audit's run_chooser:
        # activate the mapped chooser, clear any prefilled location, and allow
        # GTK's first Return to resolve completion before the final accept.
        host.activate(host.window)
        host.wait_state(lambda s:not s.get('busy') and not s.get('saving'))
        host.key('F1');wait_node('Import book','file chooser')
        host.activate(host.window_named('Import book'))
        host.key('ctrl+l','ctrl+a');host.type_text(str(path))
        wanted=hashlib.sha256(str(path).encode()).hexdigest()
        try:
            wait_until(lambda:host.section('native_import').get('entry_sha256')==wanted and host.section('native_import').get('selected_sha256')==wanted and host.section('native_import').get('accept_sensitive')=='1',15,description='actual chooser entry and native selection contain complete path')
        finally:
            (out/(label+'-chooser-typed.json')).write_text(json.dumps(dict(wanted_path_sha256=wanted,native_import=host.section('native_import'),focus=focused()),indent=2))
        capture(label+'-chooser-ready')
        host.key('Return');time.sleep(.4)
        if nodes('Import book','file chooser'):
            capture(label+'-chooser-after-first-return')
            state=host.section('native_import');(out/(label+'-chooser-before-second-return.json')).write_text(json.dumps(dict(native_import=state,focus=focused()),indent=2))
            assert state.get('selected_sha256')==wanted and state.get('accept_sensitive')=='1','Chooser selection changed after first Return; refuse blind extra acceptance'
            host.key('Return')
        wait_until(lambda:not nodes('Import book','file chooser'),40,description='native import chooser closes')
    try:
        ok,reason=bus.init();assert ok,reason
        host.launch();app=bus.wait_application('exreader-linux');host.focus_hook=lambda:json.dumps(focused())
        check('bridge',bool(nodes(role='frame')), [bus.name(x) for x in nodes(role='frame')],'actual native frame on enabled bus')
        check('scale-readback',report['environment']['gdk_window_scale']==int(os.environ['GDK_SCALE']),report['environment'],'GDK window scale equals requested scale; GTK settings recorded separately')
        check('compact-mode',host.host_state().get('compact',0)==int(a.mode=='ON'),host.host_state().get('compact',0),a.mode)
        capture('shelf')
        def tabs():
            observations=[]
            for key in ['Tab']*22+['shift+Tab']*22:
                host.key(key);observations.append(dict(key=key,focus=focused()))
            (out/'tab-cycle.json').write_text(json.dumps(observations,indent=2))
            check('tab-forward-reverse',all(x['focus'] for x in observations),observations,'Every tested Tab and reverse Tab has an exposed focus target')
            unnamed=[f for x in observations for f in x['focus'] if not f['name']]
            check('tab-focus-names',not unnamed,unnamed,'Every tested focus stop has a nonempty accessible name; original named-focus contract retained')
        phase('tab-cycle',tabs)
        def cancel():
            host.key('F1');wait_node('Import book','file chooser');capture('import-cancel-dialog');host.key('Escape')
            wait_until(lambda:not nodes('Import book','file chooser'),15)
            check('import-cancel',host.host_state().get('books',0)==0,focused(),'No book added and focus restored')
        phase('import-cancel',cancel)
        book=out/'D03.txt';book.write_text(('D03 keyboard scaling audit. Readable native page content.\n'*800))
        def import_book():
            before=host.host_state().get('generation',0);choose_file(book,'text')
            host.wait_state(lambda s:s.get('book',0)>0 and s.get('generation',0)>before and not s.get('saving'),timeout=60)
            check('keyboard-import-open',host.host_state().get('book',0)>0,host.host_state(),'Actual imported book opened with keyboard only')
        phase('import-open',import_book)
        def turn():
            before=host.host_state();host.key('F4');after=host.wait_state(lambda s:s.get('generation',0)>before.get('generation',0) and not s.get('saving'))
            check('next-page',(before.get('part'),before.get('page'),before.get('start'))!=(after.get('part'),after.get('page'),after.get('start')),[before,after],'Position changes through F4');host.key('F3');host.wait_state(lambda s:not s.get('saving'))
        phase('page-turn',turn,requires_book=True)
        menu_seen=set()
        def menu(fixed=False):
            observed=[]
            for index,parent in enumerate(('Reading','Text and notes','Library','Import')):
                host.key('alt+m','Home',*(['Down']*index),'Right');wait_node(parent,'menu');capture(('fixed-' if fixed else '')+'more-'+str(index))
                leaves=[dict(path=bus.path_of(n),role=bus.role(n),name=bus.name(n),states=bus.states(n)) for n in bus.walk(app) if bus.role(n)=='menu item']
                observed.extend(x['name'] for x in leaves)
                host.key('Escape','Escape')
            menu_seen.update(observed)
            expected=set(LEAVES) if fixed else set(LEAVES)-{'Zoom in','Zoom out'}
            check('more-22-leaves' if fixed else 'more-text-leaves',expected<=menu_seen,sorted(menu_seen),sorted(expected))
        if a.mode=='ON':phase('more-hierarchy',menu)
        else:report['pending'].append('Compact-only four More parents not applicable to default OFF')
        for name,key,title in [('search','ctrl+shift+f','Search within book'),('directory','ctrl+shift+t','Directory and page entries'),('records','ctrl+shift+r','Reading records'),('settings','ctrl+comma','Reading settings'),('collections','ctrl+shift+c','Library collections'),('account','ctrl+shift+a','Account and Sync')]:
            def dialog(key=key,title=title,name=name):
                host.key(key);wait_until(lambda:nodes(title),15,description=title);capture(name+'-dialog')
                check(name+'-dialog-focus',bool(focused()),focused(),'Dialog has actual focus')
                if name=='records':
                    tab_to('Add bookmark');host.key('Return');tab_to('Reading record text','text');host.type_text('D03 bookmark');host.key('alt+s');time.sleep(1);capture('records-saved')
                    check('record-save',bool(nodes('D03 bookmark')) or any('D03 bookmark' in bus.name(n) for n in bus.walk(app)),[bus.name(n) for n in bus.walk(app) if 'D03' in bus.name(n)],'Saved bookmark exposed in real tree')
                if name=='collections':
                    tab_to('Collection type','combo box')
                    for choice in ('Shelves','Tags','Series'):
                        host.key('Home',*(['Down']*('Shelves','Tags','Series').index(choice)))
                        time.sleep(.3);capture('collections-'+choice.lower())
                    check('collections-types-keyboard',bool(focused()),focused(),'Shelves, Tags and Series selected through native combo keyboard')
                host.key('Escape');wait_until(lambda:not nodes(title),15,description='closed '+title)
                check(name+'-escape',bool(focused()),focused(),'Focus returns after Escape')
            phase(name,dialog,requires_book=name in ('search','directory','records'))
        def notes():
            host.key('F7');wait_node('Selectable page text','text');host.key('ctrl+Home','ctrl+shift+Right','F8');host.wait_state(lambda s:not s.get('saving'));capture('notes-panel')
            check('text-note-keyboard',host.host_state().get('notes',0)>0,host.host_state(),'F7 selection and F8 save a text note');host.key('F9')
        phase('text-notes',notes,requires_book=True)
        def shelf():
            host.key('F2','ctrl+f');check('return-shelf-search',any(x['name']=='Search bookshelf' for x in focused()),focused(),'F2 then Ctrl+F reaches shelf search');host.key('Escape')
        phase('return-shelf',shelf)
        def details():
            host.key('ctrl+e');wait_until(lambda:nodes('Book details'),15,description='Book details');capture('details-dialog');host.key('Escape');wait_until(lambda:not nodes('Book details'),15)
            check('details-escape',bool(focused()),focused(),'Keyboard details closes and restores focus')
        phase('book-details',details,requires_book=True)
        if a.mode=='ON':
            def fixed_menu():
                fixture=out.parent/'fixtures/fixed/Pages.pdf'
                before=host.host_state().get('generation',0);choose_file(fixture,'pdf')
                host.wait_state(lambda s:s.get('fixed')==1 and s.get('generation',0)>before and not s.get('saving'),timeout=60)
                capture('fixed-pdf');menu(True);host.key('F2','ctrl+f')
            phase('fixed-menu-union',fixed_menu)
        command('xdotool','windowsize','--sync',host.window,'800','600');time.sleep(.4);capture('small-window')
        # Sample only the real screenshot region occupied by the shelf search.
        search=nodes('Search bookshelf')
        if search:
            box=bus.extents(search[0]);img=Image.open(out/'small-window.png').convert('RGB');crop=img.crop((max(0,box['x']),max(0,box['y']),min(img.width,box['x']+box['width']),min(img.height,box['y']+box['height'])))
            colors=crop.getcolors(crop.width*crop.height) or []
            def lum(rgb):
                c=[v/255 for v in rgb];v=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in c];return .2126*v[0]+.7152*v[1]+.0722*v[2]
            common=sorted(colors,reverse=True)[:2]
            if len(common)==2:
                levels=sorted(lum(x[1]) for x in common);report['measured_contrast']=dict(path=bus.path_of(search[0]),region=box,colors=common,ratio=(levels[1]+.05)/(levels[0]+.05),algorithm='WCAG relative sRGB luminance of two most frequent actual region colors',limitation='Not a verified text/background pair; not a contrast acceptance grant')
        report['audit_completed']=not any('error' in f for f in report['findings'])
        report['keyboard_flows_passed']=report['audit_completed'] and all(c['passed'] for c in report['checks'])
        # A real key route does not establish visible focus in every theme.
        report['keyboard_accepted']=False
    except Exception as exc:
        report['fatal']=repr(exc);report['traceback']=traceback.format_exc()
        try:
            if app is not None:capture('fatal')
        except Exception:pass
    finally:
        if host.process:
            try:host.close()
            except Exception:host.process.kill();host.process.wait()
        report['files']={str(p.relative_to(out)):dict(bytes=p.stat().st_size,sha256=digest(p)) for p in out.rglob('*') if p.is_file()}
        (out/'result.json').write_text(json.dumps(report,indent=2));print('D03 RESULT '+json.dumps({k:v for k,v in report.items() if k in ('audit_completed','keyboard_accepted','contrast_accepted','screen_reader_accepted','fatal','findings','environment')}),flush=True)
if __name__=='__main__':main()
