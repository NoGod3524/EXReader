"""Actions-only real pointer/keyboard/AT-SPI compact GTK functional checks."""
import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from check_linux_host import Session,command
import atspi_client as bus

REQUIRED=('empty-library','empty-continue-disabled','import-cancel','txt-page','epub-page','pdf-page','cbz-page',
 'reader-primary-controls','default-tools-hidden','page-keyboard-focus','more-keyboard','text-pane','text-focus',
 'comment-focus','legacy-note-add','notes-focus','legacy-note-delete','tools-close','tools-preserve-large-geometry','tools-expand-minimum','larger-smaller',
 'search-dialog','directory-dialog','records-dialog','settings-dialog','details-dialog','collections-dialog',
 'account-dialog','folder-cancel','paste-duplicate','save-retry-entry','cancel-entry','library-search',
 'back-to-library','continue-reading','closed-library-preserves-last','reopen-library','reopen-continue',
 'four-source-files-unchanged','txt-turn-pages','epub-turn-pages','pdf-turn-pages','cbz-turn-pages','pdf-zoom-menu')
MENU_ENTRIES=('Search within book…','Directory / page entries…','Reading records…','Reading settings…',
 'Larger text','Smaller text','Show or hide text and notes','Select page text','Add note from selection',
 'Saved notes','Comment','Delete selected note','Book details…','Collections…','Account / Sync…',
 'Import file…','Import folder…','Paste book files','Retry saving position','Cancel current operation','Zoom in','Zoom out')


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert os.environ.get('GITHUB_ACTIONS')=='true'
    parser=argparse.ArgumentParser()
    for name in ('payload','fixtures','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((args.fixtures/'manifest.json').read_text(encoding='utf-8'))
    checks=[];shots={};entries=[];focus=[];headers=[];app=None
    host=Session((args.payload/'bin/exreader-linux').resolve(),(args.payload/'Reader.otf').resolve(),output)
    report=dict(accepted=False,scope='optional compact GTK native UI functions only',source_sha=os.environ['GITHUB_SHA'],
        run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],checks=checks,screenshots=shots,
        menu_entries=entries,focus_observations=focus,primary_controls=headers,program_sha256=digest(host.binary),
        fixtures=manifest,compact_enabled=True,complete_product=False,performance_accepted=False,
        frame_accepted=False,six_platform_accepted=False,physical_device_execution=False,screen_reader_accepted=False)

    def wait(fn,seconds=35):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            assert host.process.poll() is None,'host exited'
            if fn():return
            time.sleep(.05)
        raise TimeoutError('compact condition: '+repr(host.read()))

    def nodes(name=None,roles=None,showing=True):
        return [node for node in bus.walk(app) if (name is None or bus.name(node)==name) and
                (roles is None or bus.role(node) in roles) and (not showing or bus.states(node).get('showing'))]

    def element(name,roles=None):
        wait(lambda:bool(nodes(name,roles)),20);return nodes(name,roles)[0]

    def click_node(node):
        box=bus.extents(node);assert box and box['width']>0 and box['height']>0
        assert bus.states(node).get('showing') and bus.states(node).get('sensitive')
        command('xdotool','mousemove','--sync',box['x']+box['width']//2,box['y']+box['height']//2)
        command('xdotool','click','1')

    def click(name,roles=None):click_node(element(name,roles))

    def idle():host.wait(lambda value:not value['saving'] and not value.get('shelf_loading',0))

    def record(name,condition=True,observed=None):
        assert name in REQUIRED and name not in [row['name'] for row in checks]
        row=dict(name=name,passed=bool(condition),observed=observed);checks.append(row)
        print(json.dumps(row,ensure_ascii=True),flush=True)
        if not condition:failure_snapshot(name)
        assert condition,row

    def failure_snapshot(label):
        try:
            path=output/('failure-'+label+'.png');command('import','-window',host.window,path)
            report.setdefault('failure_screenshots',[]).append(dict(path=path.name,sha256=digest(path)))
            (output/'failure-visibility.json').write_text(json.dumps(dict(state=host.read(),
                controls=[dict(name=bus.name(node),role=bus.role(node),states=bus.states(node),bounds=bus.extents(node))
                          for node in bus.walk(app)]),indent=2)+'\n')
        except Exception as error:report['failure_capture_error']=type(error).__name__+': '+str(error)

    def observe(section):
        parser=configparser.ConfigParser(interpolation=None);parser.read(host.observe,encoding='utf-8')
        return dict(parser[section]) if parser.has_section(section) else {}

    def geometry():
        return {key:int(value) for key,value in (line.split('=',1) for line in command('xdotool','getwindowgeometry','--shell',host.window).splitlines()) if key in ('WIDTH','HEIGHT')}

    def screenshot(name):
        path=output/(name+'.png');command('import','-window',host.window,path)
        with Image.open(path) as image:width,height=image.size
        shots[name]=dict(path=path.name,sha256=digest(path),width=width,height=height)
        assert width>=800 and height>=600

    def focus_snapshot(label):
        values=[dict(name=bus.name(node),role=bus.role(node),states=bus.states(node)) for node in bus.focused_all(app)]
        focus.append(dict(label=label,nodes=values));return values

    def menu(section,title):
        command('xdotool','windowactivate','--sync',host.window);click('More reader actions')
        if section:click(section,{'menu item'});host.key('Right')
        click(title,{'menu item'});entries.append(title)

    def modal(section,title,caption,check):
        menu(section,title);dialog=element(caption)
        wait(lambda:any(bus.is_ancestor(dialog,node) for node in bus.focused_all(app)))
        focus_snapshot(caption);screenshot(check)
        host.key('Escape');wait(lambda:not nodes(caption));idle()
        command('xdotool','windowactivate','--sync',host.window);host.key('Tab')
        value=focus_snapshot(check+'-closed')
        record(check,bool(value) and all(row['states'].get('showing') for row in value))

    def primary(reading):
        anchor=element('Back to library' if reading else 'Import book');box=bus.extents(anchor)
        found=[]
        for node in bus.walk(app):
            rect=bus.extents(node)
            if rect and bus.states(node).get('showing') and bus.role(node) in ('push button','toggle button') and abs(rect['y']-box['y'])<box['height']//2:
                found.append(bus.name(node))
        expected={'Back to library','Previous page','Next page','Contents / pages','More reader actions'} if reading else {'Import book','Continue reading','More reader actions'}
        headers.append(dict(reading=reading,actual=found));assert set(found)==expected and len(found)==len(expected),found

    def import_path(path,via_menu=False):
        before=host.read()['generation']
        if via_menu:menu('Import','Import file…')
        else:click('Import book')
        dialog=command('xdotool','search','--sync','--onlyvisible','--name','^Import book$').splitlines()[-1]
        command('xdotool','windowactivate','--sync',dialog);host.key('ctrl+l')
        chooser=element('Import book',{'file chooser'})
        entry=next(node for node in bus.walk(chooser) if bus.role(node)=='text' and bus.states(node).get('showing') and bus.states(node).get('sensitive'))
        click_node(entry);host.key('ctrl+a');host.paste(str(path.resolve()))
        wanted=hashlib.sha256(str(path.resolve()).encode()).hexdigest()
        wait(lambda:observe('native_import').get('entry_sha256')==wanted and observe('native_import').get('selected_sha256')==wanted and observe('native_import').get('accept_sensitive')=='1')
        host.key('Return');host.wait(lambda state:state['generation']>before and state['reader_visible']==1 and not state['saving'])
        wait(lambda:not nodes('Import book',{'file chooser'}));assert host.read()['error']==0

    def turn_pages(kind):
        before=tuple(host.read()[key] for key in ('part','page','start'))
        def turn(name):
            generation=host.read()['generation'];click(name)
            return host.wait(lambda value:value['generation']>generation and not value['saving'])
        value=turn('Previous page')
        assert value['error']==1 and tuple(value[key] for key in ('part','page','start'))==before
        positions=[before];parts={before[0]}
        for _ in range(64):
            value=turn('Next page');position=tuple(value[key] for key in ('part','page','start'))
            if value['error']==1:
                assert position==positions[-1];break
            assert value['error']==0 and position!=positions[-1]
            positions.append(position);parts.add(position[0])
        else:raise AssertionError('own compact fixture exceeded its 64-page functional sweep bound')
        assert len(positions)>=manifest[kind]['min_units']
        if kind in ('pdf','cbz'):assert len(positions)==manifest[kind]['pages']
        if kind=='epub':assert len(parts)==manifest[kind]['parts']
        for target in reversed(positions[:-1]):
            value=turn('Previous page');assert value['error']==0 and tuple(value[key] for key in ('part','page','start'))==target
        record(kind+'-turn-pages',host.read()['error']==0,dict(units=len(positions),parts=len(parts),first_boundary_rejected=True,last_boundary_rejected=True))

    try:
        assert bus.init()[0]
        host.launch();app=bus.wait_application('exreader-linux');idle()
        record('empty-library',host.read()['compact']==1 and host.read()['reader_visible']==0)
        primary(False);screenshot('library-empty')
        record('empty-continue-disabled',not bus.states(element('Continue reading')).get('sensitive'))
        click('Import book');element('Import book',{'file chooser'});host.key('Escape');wait(lambda:not nodes('Import book',{'file chooser'}))
        record('import-cancel',host.read()['books']==0 and host.read()['reader_visible']==0)

        source=args.fixtures/manifest['txt']['path'];import_path(source)
        primary(True);record('reader-primary-controls',True,headers[-1]);screenshot('reading-txt')
        record('txt-page',host.read()['fixed']==0 and host.read()['book']>0 and host.read()['frame_generation']>0)
        turn_pages('txt')
        record('default-tools-hidden',not nodes('Selectable page text') and not nodes('Annotation comment') and host.read()['compact_tools_open']==0)
        value=focus_snapshot('txt-page');record('page-keyboard-focus',any(row['name']=='Reading page' for row in value))
        host.key('alt+m');element('Reading',{'menu item'});host.key('Home','Right');element('Search within book…',{'menu item'})
        host.key('Escape','Escape');record('more-keyboard',bool(focus_snapshot('more-keyboard')))

        command('xdotool','windowsize','--sync',host.window,1160,920)
        wait(lambda:geometry()['WIDTH']>=1160 and geometry()['HEIGHT']>=920)
        menu('Text and notes','Show or hide text and notes');record('text-pane',bool(nodes('Selectable page text')))
        record('tools-preserve-large-geometry',geometry()['WIDTH']>=1160 and geometry()['HEIGHT']>=920,geometry())
        click('Close text and notes');command('xdotool','windowsize','--sync',host.window,900,700)
        menu('Text and notes','Show or hide text and notes')
        wait(lambda:geometry()['WIDTH']>=1040 and geometry()['HEIGHT']>=820)
        record('tools-expand-minimum',True,geometry())
        menu('Text and notes','Select page text');record('text-focus',any(bus.name(node)=='Selectable page text' for node in bus.focused_all(app)))
        menu('Text and notes','Comment');host.key('ctrl+a');host.paste('Compact note')
        record('comment-focus',any(bus.name(node)=='Annotation comment' for node in bus.focused_all(app)))
        host.key('F7','ctrl+Home','ctrl+shift+Right');menu('Text and notes','Add note from selection');host.wait(lambda state:state['notes']==1 and not state['saving'])
        record('legacy-note-add',host.read()['notes']==1)
        menu('Text and notes','Saved notes');record('notes-focus',bool(bus.focused_all(app)))
        host.key('Home');menu('Text and notes','Delete selected note');host.wait(lambda state:state['notes']==0 and not state['saving'])
        record('legacy-note-delete',host.read()['notes']==0)
        click('Close text and notes');record('tools-close',not nodes('Selectable page text') and host.read()['compact_tools_open']==0)
        before=host.read()['font'];menu('Reading','Larger text');host.wait(lambda state:state['font']>before and not state['saving'])
        menu('Reading','Smaller text');host.wait(lambda state:state['font']==before and not state['saving']);record('larger-smaller')
        for title,caption,check in [('Search within book…','Search within book','search-dialog'),
                                  ('Directory / page entries…','Directory and page entries','directory-dialog'),
                                  ('Reading records…','Reading records','records-dialog'),('Reading settings…','Reading settings','settings-dialog')]:
            modal('Reading',title,caption,check)
        menu(None,'Retry saving position');record('save-retry-entry',host.process.poll() is None and not host.read()['save_failed'])
        menu(None,'Cancel current operation');record('cancel-entry',host.process.poll() is None and not host.read()['busy'])
        click('Back to library');host.wait(lambda value:value['reader_visible']==0);primary(False);record('back-to-library')
        host.key('ctrl+f');host.key('ctrl+a');host.paste('Compact');idle()
        record('library-search',any(bus.name(node)=='Search bookshelf' for node in bus.focused_all(app)))
        host.key('ctrl+a','BackSpace');idle()
        for title,caption,check in [('Book details…','Book details','details-dialog'),('Collections…','Library collections','collections-dialog'),('Account / Sync…','Account and Sync','account-dialog')]:
            # The existing Details owner operates on the selected real shelf row.
            shelf_node=element('Bookshelf');rows=[node for node in bus.children(shelf_node) if bus.role(node)=='list item']
            if rows:
                click_node(rows[0]);idle();host.key('F2');host.wait(lambda value:value['reader_visible']==0 and not value['saving'])
            modal('Library',title,caption,check)
        menu('Import','Import folder…');element('Import folder',{'file chooser'});host.key('Escape');wait(lambda:not nodes('Import folder',{'file chooser'}));record('folder-cancel')
        uri=(source.resolve().as_uri()+'\r\n').encode()
        subprocess.run(['xclip','-selection','clipboard','-t','text/uri-list'],input=uri,check=True)
        menu('Import','Paste book files')
        wait(lambda:observe('folder_import').get('done')=='1' and observe('folder_import').get('running')=='0',60)
        record('paste-duplicate',observe('folder_import').get('duplicates')=='1' and observe('folder_import').get('failed')=='0')
        click('Stop and close');wait(lambda:observe('folder_import').get('visible')=='0' and observe('folder_import').get('owner')=='0')
        click('Continue reading');host.wait(lambda value:value['reader_visible']==1 and not value['saving']);record('continue-reading')
        for kind in ('epub','pdf','cbz'):
            host.key('F2');host.wait(lambda value:value['reader_visible']==0)
            import_path(args.fixtures/manifest[kind]['path'],via_menu=kind=='epub')
            screenshot('reading-'+kind);record(kind+'-page',host.read()['fixed']==int(manifest[kind]['fixed']) and host.read()['book']>0)
            turn_pages(kind)
            if kind=='pdf':
                zoom=host.read()['zoom'];menu('Reading','Zoom in');host.wait(lambda value:value['zoom']>zoom and not value['saving'])
                menu('Reading','Zoom out');host.wait(lambda value:value['zoom']==zoom and not value['saving']);record('pdf-zoom-menu')
        before=host.read()['book'];host.key('F2');host.wait(lambda value:value['reader_visible']==0);screenshot('library-four-formats')
        host.close();host.launch();app=bus.wait_application('exreader-linux');idle()
        record('reopen-library',host.read()['reader_visible']==0 and host.read()['compact_resume']==before)
        # Closing the library without opening Continue must retain last book.
        host.close();host.launch();app=bus.wait_application('exreader-linux');idle()
        record('closed-library-preserves-last',host.read()['compact_resume']==before)
        click('Continue reading');host.wait(lambda value:value['reader_visible']==1 and value['book']==before and not value['saving'])
        record('reopen-continue',host.read()['fixed']==1);screenshot('reading-reopened-cbz')
        record('four-source-files-unchanged',all(digest(args.fixtures/row['path'])==row['sha256'] for row in manifest.values()))
        assert set(entries)==set(MENU_ENTRIES),set(MENU_ENTRIES)-set(entries)
        assert {row['name'] for row in checks}==set(REQUIRED) and len(checks)==len(REQUIRED)
        report['accepted']=True
    except Exception as error:
        failure_snapshot('exception')
        report['failure']=type(error).__name__+': '+str(error);raise
    finally:
        if app is not None:
            (output/'atspi-tree.json').write_text(json.dumps(bus.dump(app),indent=2)+'\n')
        if host.process is not None:
            try:host.close()
            except Exception:
                host.process.kill();host.process.wait();host.log.close()
        report['count']=len(checks);(output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(dict(accepted=report['accepted'],checks=len(checks),failure=report.get('failure'))),flush=True)


if __name__=='__main__':main()
