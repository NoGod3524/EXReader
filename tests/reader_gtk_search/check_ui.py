# SPDX-License-Identifier: MIT
"""Actions-only real GTK search, stable sources, actual rows and lifecycle."""
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from check_linux_host import Session,command
import atspi_client as bus


def main():
    parser=argparse.ArgumentParser()
    for name in ('payload','fixtures','fixed-inputs','output'): parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();assert os.environ.get('GITHUB_ACTIONS')=='true'
    os.environ.pop('NO_AT_BRIDGE',None);os.environ.pop('GTK_MODULES',None);os.environ['GTK_A11Y']='atspi'
    output=args.output.resolve();output.mkdir();profile=output/'profile'
    host=Session((args.payload/'bin/exreader-linux').resolve(),(args.payload/'Reader.otf').resolve(),output)
    checks=[];report={'accepted':False,'search_scope_passed':False,'checks':checks,'source_sha':os.environ['GITHUB_SHA'],
      'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],
      'diagnostic_only':os.environ.get('GTK_SEARCH_DIAGNOSTIC_ONLY')=='true','settings_whole_page_palette_accepted':False,
      'sdk_changed':False,'product_complete':False,'performance_accepted':False,
      'program_sha256':hashlib.sha256(host.binary.read_bytes()).hexdigest()}
    originals={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for root in (args.fixtures,args.fixed_inputs) for p in root.iterdir() if p.is_file()}

    def observed(section='inbook_search'):
        value=configparser.ConfigParser(interpolation=None);value.read(host.observe)
        return dict(value[section]) if value.has_section(section) else {}

    def wait(predicate=lambda value:True,idle=True,seconds=30):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            assert host.process.poll() is None,'host exited'
            value=observed()
            if value and (not idle or (value['running']=='0' and not host.read()['busy'] and not host.read()['saving'])) and predicate(value): return value
            time.sleep(.02)
        raise TimeoutError('search state: '+repr(observed())+' host: '+repr(host.read()))

    def element(name,roles=None):
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            value=next((node for node in bus.walk(app) if (roles is None or bus.role(node) in roles) and bus.name(node)==name),None)
            if value:return value
            time.sleep(.05)
        raise TimeoutError('missing native control: '+name)

    def click_accessible(value):
        rectangle=bus.extents(value);assert rectangle and rectangle['width']>0 and rectangle['height']>0
        command('xdotool','mousemove','--sync',str(rectangle['x']+rectangle['width']//2),str(rectangle['y']+rectangle['height']//2))
        command('xdotool','click','1')

    def click(name,roles=None):click_accessible(element(name,roles))

    def record(name,condition=True,actual=None):
        value={'name':name,'pass':bool(condition),'observed':actual};checks.append(value);print(json.dumps(value),flush=True);assert condition,value

    def import_book(path):
        path=path.resolve();before=host.read()['generation'];deadline=time.monotonic()+30;host.key('F1')
        window=command('xdotool','search','--sync','--onlyvisible','--name','^Import book$').splitlines()[-1]
        command('xdotool','windowactivate','--sync',window)
        def native_ready(predicate):
            while time.monotonic()<deadline:
                assert host.process.poll() is None,'host exited during chooser transition: '+str(host.process.returncode)
                value=observed('native_import')
                if predicate(value):return
                time.sleep(.02)
            raise TimeoutError('native import focus/input not ready: '+repr(observed('native_import')))
        native_ready(lambda value:value.get('visible')=='1' and value.get('active')=='1')
        host.key('ctrl+l')
        chooser=element('Import book',{'file chooser'})
        location=None
        while time.monotonic()<deadline:
            location=next((node for node in bus.walk(chooser) if bus.role(node)=='text' and bus.states(node).get('showing') and bus.states(node).get('sensitive')),None)
            if location:break
            assert host.process.poll() is None,'host exited before native location entry'
            time.sleep(.02)
        assert location,'visible native location entry absent'
        click_accessible(location);native_ready(lambda value:value.get('entry_focused')=='1')
        host.key('ctrl+a');host.paste(str(path));expected=hashlib.sha256(str(path).encode()).hexdigest()
        while time.monotonic()<deadline:
            assert host.process.poll() is None,'host exited during source selection: '+str(host.process.returncode)
            value=observed('native_import')
            if value.get('visible')=='1' and value.get('entry_sha256')==expected and value.get('selected_sha256')==expected and value.get('accept_sensitive')=='1':break
            time.sleep(.02)
        else:raise TimeoutError('native source selection not ready: '+repr(observed('native_import')))
        host.key('Return');host.wait(lambda value:value['generation']>before and not value['saving'] and observed('native_import').get('visible')=='0',timeout=max(.1,deadline-time.monotonic()))
        assert not host.read()['error'];return host.read()['book']

    def open_search():
        command('xdotool','windowactivate','--sync',host.window);host.key('ctrl+shift+f')
        wait(lambda value:value['visible']=='1')
        window=command('xdotool','search','--onlyvisible','--name','^Search within book$').splitlines()[-1]
        command('xdotool','windowactivate','--sync',window);return element('Search within book',{'dialog'})

    def close_search():host.key('Escape');wait(lambda value:value['visible']=='0')

    def query(text):
        click('In-book query',{'text'});host.key('ctrl+a');host.paste(text);before=int(observed()['actions'])
        host.key('alt+s');return wait(lambda value:int(value['actions'])>before)

    def active_long_scan():
        # These controls live for this dialog. Capture native cancel bounds
        # before scanning so accessibility enumeration cannot consume the scan.
        cancel_bounds=bus.extents(element('Cancel search',{'push button'}))
        click('In-book query',{'text'});host.paste('ABSENT_QUERY_FOR_FULL_CHAPTER_SCAN')
        before_actions=int(observed()['actions']);host.key('alt+s')
        scanning=wait(lambda value:value['phase']=='2' and int(value['polls'])>0 and int(value['actions'])>before_actions,idle=False,seconds=10)
        return scanning,cancel_bounds

    def rows():return [row for row in bus.children(element('In-book results')) if bus.role(row)=='list item' and bus.name(row).startswith('Search result ')]

    def choose(index):
        selected=next(row for row in rows() if bus.name(row).startswith('Search result '+str(index+1)+':'))
        before=int(observed()['actions'])
        window=command('xdotool','search','--onlyvisible','--name','^Search within book$').splitlines()[-1]
        command('xdotool','windowactivate','--sync',window)
        deadline=time.monotonic()+10;previous=None;requested=False
        while time.monotonic()<deadline:
            rectangle=bus.extents(selected);states=bus.states(selected)
            if (rectangle and rectangle['width']>50 and rectangle['height']>=12 and
                    states.get('showing') and states.get('sensitive')):
                if not requested:
                    assert selected.get_component_iface().grab_focus(),'native result refused focus'
                    requested=True
                elif states.get('focused') and rectangle==previous:
                    assert int(observed()['actions'])==before,'focus unexpectedly activated a result'
                    report.setdefault('row_clicks',[]).append(dict(index=index,rectangle=rectangle,states=states))
                    click_accessible(selected)
                    break
                previous=rectangle
            time.sleep(.02)
        else:raise TimeoutError('native result focus/allocation not ready: '+str(index))
        return wait(lambda value:int(value['actions'])>before)

    def storage(notes_only=False):
        values={}
        for name in ('library.sqlite','library.sqlite.product.sqlite'):
            path=profile/name
            if not path.exists():continue
            with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as database:
                if notes_only and name=='library.sqlite':
                    tables=[row[0] for row in database.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%note%'")]
                    body=[(table,sorted(database.execute('SELECT * FROM "'+table.replace('"','""')+'"').fetchall(),key=repr)) for table in tables]
                else:body=sorted(database.iterdump())
            values[name]=hashlib.sha256(repr(body).encode()).hexdigest()
        return values

    def frame():
        value=host.read();return {key:value[key] for key in ('book','part','page','start','end','font','zoom','notes','selection_start','selection_end','frame_generation')}

    def image(name):
        path=output/(name+'.png');command('import','-window',host.window,str(path));value=host.read();prefs=observed('preferences')
        width,height=int(prefs['bitmap_width']),int(prefs['bitmap_height']);x=value['page_x']+(value['page_width']-width)//2;y=value['page_y']+(value['page_height']-height)//2
        pixels=Image.open(path).convert('RGB').crop((x,y,x+width,y+height)).tobytes();return hashlib.sha256(pixels).hexdigest()

    try:
        assert bus.init()[0];host.launch();app=bus.wait_application('exreader-linux');wait()
        txt=import_book(args.fixtures/'book.txt')
        host.key('F7','ctrl+Home','ctrl+shift+Right','F11');host.paste('Existing native note');host.key('F8');host.wait(lambda value:value['notes']==1)
        before=frame();saved=storage();pixels=image('before-search')
        dialog=open_search();focused=bus.focused_all(app)
        record('native_modal_has_named_query_focus',bus.states(dialog).get('modal') and any(bus.name(node)=='In-book query' for node in focused))
        command('xdotool','windowactivate','--sync',host.window);host.key('F4','F1')
        record('modal_blocks_background_reading_and_import',frame()==before and not bus.find_one(app,text='Import book',roles={'file chooser'}))
        window=command('xdotool','search','--onlyvisible','--name','^Search within book$').splitlines()[-1];command('xdotool','windowactivate','--sync',window)
        result=query('');record('empty_query_is_visible_refusal_without_navigation',int(result['code'])==2 and result['count']=='0' and frame()==before)
        result=query('Z-hit');labels=[];counts=[]
        while True:
            count=int(result['count']);counts.append(count);labels.extend(bus.name(row) for row in rows())
            if result['complete']=='1':break
            actions=int(result['actions']);host.key('alt+m');result=wait(lambda value:int(value['actions'])>actions)
        indices=[int(re.search(r'\[Z-hit\]\s+(\d{3})',label)[1]) for label in labels]
        record('250_actual_result_rows_continue_in_32_row_pages',counts==[32]*7+[26] and indices==list(range(250)),{'batches':counts,'indices':indices})
        record('query_and_all_batches_preserve_current_reading_notes_and_revisions',frame()==before and storage()==saved)
        result=query('🙂');record('unicode_emoji_query_uses_utf8',result['count']=='3' and result['code']=='0')
        result=query('not in this source');record('no_matches_complete_without_navigation',result['count']=='0' and result['complete']=='1' and frame()==before)
        result=query('AMBIGUOUS TARGET');record('ambiguous_quote_returns_actual_named_rows',result['count']=='2' and len(rows())==2)
        selected=choose(0);record('selected_ambiguous_txt_result_does_not_jump',selected['match']=='2' and selected['visible']=='1' and frame()==before and storage()==saved)
        close_search();record('read_only_close_preserves_actual_page_pixels_and_storage',frame()==before and storage()==saved and image('after-search-close')==pixels)
        notes=storage(True);open_search();query('书内搜索');choose(0)
        record('unicode_found_selection_uses_utf8_byte_boundaries',observed()['visible']=='0' and host.read()['selected']==len('书内搜索') and host.read()['selection_end']-host.read()['selection_start']==len('书内搜索'.encode()) and storage(True)==notes,frame())
        open_search();query('Z-hit 220');choose(0)
        record('explicit_txt_found_navigates_after_independent_resolve',host.read()['book']==txt and host.read()['start']>before['start'] and host.read()['selected']==len('Z-hit 220') and storage(True)==notes,{'frame':frame(),'selected_characters':host.read()['selected'],'notes_and_product_unchanged':storage(True)==notes})
        epub=import_book(args.fixtures/'book.epub')
        for target_font in (26,28):
            previous_generation=host.read()['generation'];host.key('F5')
            host.wait(lambda value:value['font']==target_font and value['generation']>previous_generation and not value['saving'])
        prior=frame();saved=storage();open_search();result=query('SEARCHTOKEN')
        record('bounded_epub_has_distinct_repeated_spine_result_rows',result['count']=='4' and any('Part 3' in bus.name(row) for row in rows()) and frame()==prior)
        close_search();record('epub_query_preserves_current_28_font_pager_and_storage',frame()==prior and storage()==saved)
        open_search();query('SEARCHTOKEN');choose(3)
        record('repeated_spine_found_navigation_keeps_explicit_unit_and_font',host.read()['book']==epub and host.read()['part']==2 and host.read()['font']==28 and host.read()['selected']==len('SEARCHTOKEN'),frame())
        open_search();query('unique-b-only');choose(0)
        record('epub_unique_result_navigates_to_other_spine',host.read()['part']==1 and host.read()['font']==28)
        pdf=import_book(args.fixtures/'pages.pdf');prior=frame();saved=storage();open_search();result=query('Shared quote')
        record('fixed_text_search_paginates_pages_without_changing_reader',result['count']=='2' and frame()==prior and storage()==saved)
        choose(1);record('fixed_found_uses_page_id_route_and_actual_sdk_frame',host.read()['book']==pdf and host.read()['page']==3 and host.read()['selected']==len('Shared quote'),frame())
        prior=frame();saved=storage();open_search();query('selection target');selected=choose(0)
        record('fixed_ambiguous_result_has_no_offset_or_page_fallback',selected['match']=='2' and frame()==prior and storage()==saved);close_search()
        import_book(args.fixtures/'empty.pdf');prior=frame();saved=storage();open_search();result=query('word')
        record('pdf_without_text_is_complete_empty_and_never_jumps',result['count']=='0' and result['complete']=='1' and frame()==prior and storage()==saved);close_search()
        import_book(args.fixed_inputs/'Pages.cbz');prior=frame();saved=storage();open_search();result=query('word')
        record('cbz_no_text_provider_is_visible_sdk_refusal',result['code']=='4' and result['count']=='0' and frame()==prior and storage()==saved);close_search()
        import_book(args.fixtures/'cancel.epub');prior=frame();saved=storage();open_search()
        scanning,cancel_bounds=active_long_scan()
        command('xdotool','mousemove','--sync',str(cancel_bounds['x']+cancel_bounds['width']//2),str(cancel_bounds['y']+cancel_bounds['height']//2));command('xdotool','click','1')
        cancelled=wait(lambda value:value['running']=='0' and value['code']=='5')
        record('actual_module_control_poll_cancels_without_mutating_reading',int(scanning['polls'])>0 and frame()==prior and storage()==saved,{'during':scanning,'after':cancelled})
        close_search();open_search();record('closed_query_is_not_resumed_or_repopulated',observed()['count']=='0' and observed()['complete']=='1')
        active_long_scan();close_search()
        record('escape_during_actual_module_scan_retires_search_and_keeps_reader',frame()==prior and storage()==saved and observed()['count']=='0')
        open_search();active_long_scan();command('wmctrl','-ic',hex(int(host.window)))
        close_code=host.process.wait(timeout=20);host.log.close()
        record('parent_window_close_during_actual_scan_retires_owner_before_exit',close_code==0 and observed()['visible']=='0' and storage()==saved)
        host.launch();app=bus.wait_application('exreader-linux');wait();prior=frame()
        record('real_reopen_after_active_search_close_has_no_query_or_storage_change',observed()['visible']=='0' and observed()['count']=='0' and storage()==saved)
        open_search();active_long_scan()
        command('xdotool','windowminimize',host.window);wait(lambda value:value['visible']=='0')
        command('xdotool','windowmap',host.window);command('xdotool','windowactivate','--sync',host.window)
        record('background_minimize_cancels_and_dismisses_without_resume',frame()==prior and storage()==saved and observed()['count']=='0')
        import_book(args.fixtures/'book.txt');open_search();result=query('书内搜索')
        record('switching_book_creates_fresh_source_and_cannot_reuse_old_rows',result['count']=='1' and host.read()['book']==txt);close_search()
        saved=storage();host.close();host.launch();app=bus.wait_application('exreader-linux');wait()
        record('actual_process_restart_does_not_restore_search_state',observed()['visible']=='0' and observed()['count']=='0' and storage()==saved)
        record('all_original_fixture_bytes_remain_unchanged',all(hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest for path,digest in originals.items()))
        report.update(search_scope_passed=True,count=len(checks),passed=len(checks),failed=0)
    finally:
        if not report['search_scope_passed']:
            report['host_returncode_before_cleanup']=host.process.poll() if host.process else None
            report['failure_host']=host.read() if host.observe.exists() else {}
            if (output/'application.log').exists():print((output/'application.log').read_text(errors='replace')[-6000:],flush=True)
        if host.process and host.process.poll() is None:
            if not report['search_scope_passed']:
                if 'app' in locals():(output/'failure-tree.json').write_text(json.dumps(bus.dump(app),indent=2),encoding='utf-8')
            host.process.kill();host.process.wait(timeout=15)
        if host.log:host.log.close()
        report['last_observation']=observed();(output/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8');bus.exit_bus()
    print(json.dumps(report),flush=True)
    raise SystemExit(0 if report['search_scope_passed'] else 1)


if __name__=='__main__':main()
