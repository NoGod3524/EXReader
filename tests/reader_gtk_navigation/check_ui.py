# SPDX-License-Identifier: MIT
"""Actions-only native GTK directory, explicit targets and lifecycle."""
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_linux_host import Session, command
import atspi_client as bus


def main():
    parser=argparse.ArgumentParser()
    for name in ('payload','fixtures','fixed-inputs','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();assert os.environ.get('GITHUB_ACTIONS')=='true'
    os.environ.pop('NO_AT_BRIDGE',None);os.environ.pop('GTK_MODULES',None);os.environ['GTK_A11Y']='atspi'
    output=args.output.resolve();output.mkdir();profile=output/'profile'
    host=Session((args.payload/'bin/exreader-linux').resolve(),(args.payload/'Reader.otf').resolve(),output)
    checks=[];report={'accepted':False,'navigation_scope_passed':False,'checks':checks,'source_sha':os.environ['GITHUB_SHA'],
      'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],'sdk_changed':False,
      'diagnostic_only':os.environ.get('GTK_NAVIGATION_DIAGNOSTIC_ONLY')=='true','settings_whole_page_palette_accepted':False,
      'complete_product':False,'performance_accepted':False,'program_sha256':hashlib.sha256(host.binary.read_bytes()).hexdigest()}
    originals={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for root in (args.fixtures,args.fixed_inputs) for p in root.iterdir() if p.is_file()}
    def launch():
        # Establish the native test fixture before the unchanged host deadline.
        end=time.monotonic()+10
        while time.monotonic()<end:
            manager=subprocess.run(['wmctrl','-m'],text=True,capture_output=True,timeout=2)
            if manager.returncode==0 and 'Name: Openbox' in manager.stdout:break
            time.sleep(.05)
        else:raise TimeoutError('Openbox fixture not ready: '+manager.stdout+manager.stderr)
        try:host.launch()
        except BaseException:
            for name,argv in [('window-tree',['xwininfo','-root','-tree']),('window-list',['wmctrl','-lpG']),('window-manager',['wmctrl','-m'])]:
                data=subprocess.run(argv,text=True,capture_output=True,timeout=5);body=data.stdout+data.stderr
                (output/(name+'.txt')).write_text(body);print(name+': '+body,flush=True)
            matches=subprocess.run(['xdotool','search','--onlyvisible','--name','^EXReader Linux$'],text=True,capture_output=True,timeout=5)
            print('expected_pid='+str(host.process.pid)+' title_windows='+matches.stdout,flush=True)
            for native in matches.stdout.splitlines():
                data=subprocess.run(['xprop','-id',native,'_NET_WM_PID','WM_NAME','WM_CLASS','WM_STATE','_NET_WM_STATE'],text=True,capture_output=True,timeout=5)
                (output/('window-'+native+'.txt')).write_text(data.stdout+data.stderr);print(data.stdout+data.stderr,flush=True)
            raise
    def observed(section='directory'):
        value=configparser.ConfigParser(interpolation=None);value.read(host.observe)
        return dict(value[section]) if value.has_section(section) else {}
    scan_inputs=[]
    def wait(predicate=lambda value:True,idle=True,seconds=30,interval=.02):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            assert host.process.poll() is None,'host exited';value=observed()
            if value and (not idle or (value['running']=='0' and not host.read()['busy'] and not host.read()['saving'])) and predicate(value):return value
            time.sleep(interval)
        raise TimeoutError('directory: '+repr(observed())+' host: '+repr(host.read()))
    def element(name,roles=None):
        end=time.monotonic()+20
        while time.monotonic()<end:
            node=next((node for node in bus.walk(app) if bus.name(node)==name and (roles is None or bus.role(node) in roles)),None)
            if node:return node
            time.sleep(.02)
        raise TimeoutError('missing native control: '+name)
    def click_node(node):
        rect=bus.extents(node);assert rect and rect['width']>0 and rect['height']>0
        command('xdotool','mousemove','--sync',str(rect['x']+rect['width']//2),str(rect['y']+rect['height']//2));command('xdotool','click','1')
    def click(name,roles=None):click_node(element(name,roles))
    def record(name,condition=True,actual=None):
        value={'name':name,'pass':bool(condition),'observed':actual};checks.append(value);print(json.dumps(value),flush=True);assert condition,value
    def import_book(path):
        path=path.resolve();prior=host.read()['generation'];end=time.monotonic()+30;host.key('F1')
        chooser_window=command('xdotool','search','--sync','--onlyvisible','--name','^Import book$').splitlines()[-1]
        command('xdotool','windowactivate','--sync',chooser_window)
        def native(predicate):
            while time.monotonic()<end:
                assert host.process.poll() is None,'host exited during chooser';value=observed('native_import')
                if predicate(value):return
                time.sleep(.02)
            raise TimeoutError('native import: '+repr(observed('native_import')))
        native(lambda v:v.get('active')=='1');host.key('ctrl+l');chooser=element('Import book',{'file chooser'})
        entry=next(node for node in bus.walk(chooser) if bus.role(node)=='text' and bus.states(node).get('showing') and bus.states(node).get('sensitive'))
        click_node(entry);native(lambda v:v.get('entry_focused')=='1');host.key('ctrl+a');host.paste(str(path));digest=hashlib.sha256(str(path).encode()).hexdigest()
        native(lambda v:v.get('entry_sha256')==digest and v.get('selected_sha256')==digest and v.get('accept_sensitive')=='1')
        host.key('Return');host.wait(lambda v:v['generation']>prior and not v['saving'] and observed('native_import').get('visible')=='0',timeout=max(.1,end-time.monotonic()))
        assert not host.read()['error'];return host.read()['book']
    def open_directory(idle=True):
        command('xdotool','windowactivate','--sync',host.window);host.key('ctrl+shift+t');value=wait(lambda v:v['visible']=='1',idle=idle)
        if not idle:return value
        window=command('xdotool','search','--onlyvisible','--name','^Directory and page entries$').splitlines()[-1]
        command('xdotool','windowactivate','--sync',window);return value
    def close_directory():host.key('Escape');wait(lambda v:v['visible']=='0')
    def rows():return [node for node in bus.children(element('Directory entries')) if bus.role(node)=='list item']
    def select(index,candidate=False):
        prefix=('Spine item ' if candidate else 'Directory entry ')+str(index+1)
        node=next(node for node in rows() if bus.name(node)==prefix or bus.name(node).startswith(prefix+':'))
        end=time.monotonic()+10
        while time.monotonic()<end:
            rect=bus.extents(node);states=bus.states(node)
            if rect and rect['width']>50 and rect['height']>=12 and states.get('showing') and states.get('sensitive'):break
            time.sleep(.02)
        else:raise TimeoutError('native row has no actionable allocation: '+prefix)
        click_node(node)
        wait(lambda v:v['selected']==str(index) and v['open_sensitive']=='1')
    def action(keys):
        before=int(observed()['actions']);host.key(keys);return wait(lambda v:int(v['actions'])>before)
    def choose(index,candidate=False):select(index,candidate);return action('alt+o')
    def storage(notes_only=False):
        result={}
        for name in ('library.sqlite','library.sqlite.product.sqlite'):
            path=profile/name
            if not path.exists():continue
            with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
                if notes_only and name=='library.sqlite':
                    tables=[row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%note%'")]
                    body=[(table,sorted(db.execute('SELECT * FROM "'+table+'"').fetchall(),key=repr)) for table in tables]
                else:body=sorted(db.iterdump())
            result[name]=hashlib.sha256(repr(body).encode()).hexdigest()
        return result
    def frame():
        value=host.read();return {key:value[key] for key in ('book','part','page','start','end','font','zoom','notes','selection_start','selection_end','frame_generation')}
    def image(name):
        path=output/(name+'.png');command('import','-window',host.window,str(path));value=host.read();prefs=observed('preferences')
        width,height=int(prefs['bitmap_width']),int(prefs['bitmap_height']);x=value['page_x']+(value['page_width']-width)//2;y=value['page_y']+(value['page_height']-height)//2
        return hashlib.sha256(Image.open(path).convert('RGB').crop((x,y,x+width,y+height)).tobytes()).hexdigest()
    def cfi(name):
        click('Full EPUB CFI',{'text'});host.key('ctrl+a');host.paste((args.fixtures/name).read_text());return action('Return')
    def active_directory():
        command('xdotool','windowactivate','--sync',host.window)
        # Observe the real operation while the native input process is still
        # dispatching, instead of starting the observer after it returns.
        scan_inputs.append(subprocess.Popen(['xdotool','key','--clearmodifiers','--delay','0','ctrl+shift+t'],
                                            stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True))
        return wait(lambda v:v['phase']=='2' and int(v['polls'])>0,idle=False,seconds=15,interval=.001)
    try:
        assert bus.init()[0];launch();app=bus.wait_application('exreader-linux');wait()
        book=import_book(args.fixtures/'nav3.epub');host.key('F7','ctrl+Home','ctrl+shift+Right','F11');host.paste('Existing native directory note');host.key('F8');host.wait(lambda v:v['notes']==1)
        for font in (26,28):host.key('F5');host.wait(lambda v:v['font']==font and not v['saving'])
        prior=frame();saved=storage();pixels=image('before-directory');open_directory();dialog=element('Directory and page entries',{'dialog'})
        record('actual_named_modal_has_ten_ordered_root_entries',bus.states(dialog).get('modal') and len(rows())==10 and [bus.name(n).split(':')[0] for n in rows()]==['Directory entry '+str(i) for i in (1,3,6,7,8,9,10,11,12,13)])
        record('author_label_is_literal_text_with_no_markup_execution',any(bus.name(n).endswith('<script>alert(1)</script> label') for n in rows()) and frame()==prior and storage()==saved)
        command('xdotool','windowactivate','--sync',host.window);host.key('F1','F4')
        record('directory_modal_blocks_background_import_and_reading',frame()==prior and not bus.find_one(app,text='Import book',roles={'file chooser'}))
        directory_window=command('xdotool','search','--onlyvisible','--name','^Directory and page entries$').splitlines()[-1];command('xdotool','windowactivate','--sync',directory_window)
        select(0);action('alt+h');record('actual_child_level_preserves_unicode_and_sdk_parent',len(rows())==1 and bus.name(rows()[0]).endswith('子节 🙂') and observed()['parent']=='0')
        action('alt+b');select(2);action('alt+h');choose(3)
        record('external_link_stays_visible_and_does_not_open_or_change_reading',observed()['code']=='12' and frame()==prior and storage()==saved)
        action('alt+b');choose(8);record('unsafe_target_refuses_without_fallback',observed()['code']=='7' and frame()==prior and storage()==saved)
        choose(7);record('missing_target_refuses_without_fallback',observed()['code']=='9' and frame()==prior and storage()==saved)
        close_directory();record('read_only_browsing_close_preserves_pixels_notes_progress_and_product',frame()==prior and storage()==saved and image('after-directory')==pixels)
        notes=storage(True);open_directory();select(0);action('alt+h');choose(1)
        record('actual_unicode_fragment_uses_independent_found_and_correct_spine',observed()['visible']=='0' and observed()['match']=='1' and host.read()['book']==book and host.read()['part']==1 and host.read()['position']==0 and host.read()['font']==28 and storage(True)==notes,frame())
        open_directory();choose(5);prior=frame();saved=storage()
        record('missing_fragment_requires_explicit_part_start_confirmation',observed()['code']=='13' and frame()==prior and storage()==saved)
        action('alt+p');record('explicit_part_start_is_reverified_and_found',observed()['visible']=='0' and observed()['match']=='1' and host.read()['part']==2)
        book=import_book(args.fixtures/'repeated.epub');prior=frame();saved=storage();open_directory();choose(0)
        record('repeated_spine_lists_all_explicit_candidates_without_jumping',observed()['candidate_mode']=='1' and observed()['selected']==str(2**64-1) and observed()['open_sensitive']=='0' and [bus.name(n) for n in rows()]==['Spine item 1','Spine item 2'] and all(not bus.states(n).get('selected') for n in rows()) and frame()==prior and storage()==saved)
        choose(1,True);record('second_repeated_spine_item_remains_second_after_found',observed()['visible']=='0' and host.read()['book']==book and host.read()['part']==1 and observed()['match']=='1')
        book=import_book(args.fixtures/'ncx2.epub');open_directory();select(0);action('alt+h');choose(1)
        record('actual_ncx_unicode_fragment_uses_same_public_verification',observed()['visible']=='0' and host.read()['book']==book and host.read()['part']==1)
        import_book(args.fixtures/'many.epub');prior=frame();saved=storage();open_directory();labels=[bus.name(n) for n in rows()];action('alt+m');labels += [bus.name(n) for n in rows()]
        record('forty_five_roots_use_actual_32_then_13_row_pages',len(labels)==45 and all(label.endswith('Root %03d'%i) for i,label in enumerate(labels)) and observed()['next']==str(2**64-1) and frame()==prior and storage()==saved);close_directory()
        import_book(args.fixtures/'unicode.epub');prior=frame();saved=storage();open_directory();cfi('surrogate.cfi')
        record('surrogate_interior_cfi_is_not_guessed_to_utf8',observed()['visible']=='1' and frame()==prior and storage()==saved)
        cfi('collapsed.cfi');record('collapsed_raw_cfi_is_not_guessed_to_normalized_offset',observed()['visible']=='1' and frame()==prior and storage()==saved)
        cfi('normal.cfi');record('full_cfi_maps_only_verified_scalar_and_projection_then_found',observed()['visible']=='0' and observed()['match']=='1' and host.read()['part']==1 and host.read()['position']==2)
        import_book(args.fixtures/'empty.epub');prior=frame();saved=storage();open_directory();record('no_authored_directory_is_explicit_empty',not rows() and observed()['total']=='0' and frame()==prior and storage()==saved);close_directory()
        book=import_book(args.fixtures/'pages.pdf');prior=frame();saved=storage();open_directory()
        record('pdf_is_page_entries_and_never_exposes_authored_outlines',observed()['kind']=='2' and bus.find_one(app,text='By-page entries · not an author outline',roles={'label'}) is not None and len(rows())==3 and all('Authored Outline' not in bus.name(n) for n in rows()) and frame()==prior and storage()==saved)
        choose(2);record('pdf_explicit_page_id_is_independently_verified_before_frame',observed()['visible']=='0' and observed()['verified']=='1' and host.read()['book']==book and host.read()['page']==2)
        book=import_book(args.fixed_inputs/'Pages.cbz');open_directory();choose(1)
        record('cbz_page_identity_opens_without_fabricating_text_outline',observed()['visible']=='0' and observed()['verified']=='1' and host.read()['book']==book and host.read()['page']==1)
        import_book(args.fixtures/'cancel.epub');prior=frame();saved=storage();scanning=active_directory();command('xdotool','key','--clearmodifiers','--delay','0','alt+n');wait(lambda v:v['running']=='0' and v['code']=='4')
        record('actual_control_poll_cancel_keeps_reader_and_storage',int(scanning['polls'])>0 and frame()==prior and storage()==saved);close_directory()
        active_directory();close_directory();record('escape_during_actual_directory_scan_discards_late_rows',observed()['visible']=='0' and frame()==prior and storage()==saved)
        active_directory();command('xdotool','windowminimize',host.window);wait(lambda v:v['visible']=='0');command('xdotool','windowmap',host.window);command('xdotool','windowactivate','--sync',host.window)
        record('background_closes_directory_without_resuming_stale_snapshot',frame()==prior and storage()==saved)
        active_directory();command('wmctrl','-ic',hex(int(host.window)));code=host.process.wait(timeout=20);host.log.close()
        record('parent_close_during_actual_scan_retires_owner_before_exit',code==0 and observed()['visible']=='0' and storage()==saved)
        launch();app=bus.wait_application('exreader-linux');wait();record('real_process_reopen_has_no_directory_or_cfi_resume',observed()['visible']=='0' and storage()==saved)
        import_book(args.fixtures/'nav3.epub');open_directory();record('switching_books_rebuilds_source_bound_directory',len(rows())==10 and observed()['candidate_mode']=='0');close_directory()
        record('all_navigation_original_bytes_are_unchanged',all(hashlib.sha256(Path(name).read_bytes()).hexdigest()==sha for name,sha in originals.items()))
        report.update(navigation_scope_passed=True,count=len(checks),passed=len(checks),failed=0)
    finally:
        report['scan_input_processes']=[]
        for trigger in scan_inputs:
            try:_,error=trigger.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                trigger.kill();_,error=trigger.communicate()
            report['scan_input_processes'].append(dict(pid=trigger.pid,returncode=trigger.returncode,error=error))
            if trigger.returncode!=0:report['navigation_scope_passed']=False
        if not report['navigation_scope_passed']:
            report['host_returncode_before_cleanup']=host.process.poll() if host.process else None
            report['failure_host']=host.read() if host.observe.exists() else {}
            if (output/'application.log').exists():print((output/'application.log').read_text(errors='replace')[-6000:],flush=True)
        if host.process and host.process.poll() is None:
            if not report['navigation_scope_passed'] and 'app' in locals():(output/'failure-tree.json').write_text(json.dumps(bus.dump(app),indent=2))
            host.process.kill();host.process.wait(timeout=15)
        if host.log:host.log.close()
        report['last_observation']=observed();(output/'result.json').write_text(json.dumps(report,indent=2));bus.exit_bus()
    print(json.dumps(report),flush=True);raise SystemExit(0 if report['navigation_scope_passed'] else 1)


if __name__=='__main__':main()
