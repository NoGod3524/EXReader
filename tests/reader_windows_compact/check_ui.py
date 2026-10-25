"""Actions-only observations of the actual compact host, native menus and picker."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback
from contract import FORMATS,REQUIRED,validate

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/reader_windows_preferences'))
import check_ui as P
U=P.U;send=P.send;A=P.A
U.GetSubMenu.argtypes=[W.HANDLE,C.c_int];U.GetSubMenu.restype=W.HANDLE
U.GetMenuItemID.argtypes=[W.HANDLE,C.c_int];U.GetMenuItemID.restype=W.UINT
U.GetParent.argtypes=[W.HWND];U.GetParent.restype=W.HWND
U.GetDlgCtrlID.argtypes=[W.HWND];U.GetDlgCtrlID.restype=C.c_int
U.EnumChildWindows.argtypes=[W.HWND,P.ENUM,W.LPARAM]


def visible(app,identifier):return bool(U.IsWindowVisible(U.GetDlgItem(app.window,identifier)))


def menu_ids(menu):
    found=set()
    for i in range(U.GetMenuItemCount(menu)):
        child=U.GetSubMenu(menu,i)
        if child:found.update(menu_ids(child))
        else:found.add(U.GetMenuItemID(menu,i))
    return found


def owned_dialog(app,child=None):
    found=[]
    @P.ENUM
    def visit(window,unused):
        pid=W.DWORD();U.GetWindowThreadProcessId(window,C.byref(pid))
        if pid.value==app.process.pid and window!=app.window and U.IsWindowVisible(window):
            name=C.create_unicode_buffer(100);U.GetClassNameW(window,name,100)
            if (child is not None and U.GetDlgItem(window,child)) or (child is None and name.value=='#32770' and U.GetDlgItem(window,1)):
                found.append(window)
        return True
    U.EnumWindows(visit,0)
    return found[-1] if found else None


def picker(app,path=None):
    app.focus();A.tap(ord('O'),(A.VK_CONTROL,))
    dialog=app.wait(lambda:owned_dialog(app),timeout=20)
    if path is None:
        send(dialog,0x111,2);app.wait(lambda:not U.IsWindow(dialog));return
    candidates=[]
    @P.ENUM
    def child(window,unused):
        name=C.create_unicode_buffer(100);U.GetClassNameW(window,name,100)
        if name.value=='Edit' and U.IsWindowVisible(window):
            parent=window
            for _ in range(5):
                if U.GetDlgCtrlID(parent) in (1148,1152):candidates.append(window);break
                parent=U.GetParent(parent)
                if not parent or parent==dialog:break
        return True
    U.EnumChildWindows(dialog,child,0)
    assert len(candidates)==1,('native filename edit',len(candidates))
    P.set_text(candidates[0],str(path.resolve()));send(dialog,0x111,1)
    app.wait(lambda:not U.IsWindow(dialog),timeout=30);app.wait_idle()


def command(app,identifier):send(app.window,0x111,identifier)


def main():
    assert os.name=='nt' and os.environ.get('GITHUB_ACTIONS')=='true'
    parser=argparse.ArgumentParser()
    for name in ('candidate','font','fixtures','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    result=dict(accepted=False,source_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],
        consumer_sha256=hashlib.sha256(args.candidate.read_bytes()).hexdigest(),checks=[],problems=[],count=0,
        acceptance_scope='independent Windows native compact UI candidate on four formats',performance_accepted=False,complete_product=False)
    app=None
    def record(name):result['checks'].append(dict(name=name,passed=True,pid=app.process.pid))
    def shot(name):P.M.screenshot(app.window,out/name)
    try:
        for kind,filename in FORMATS.items():
            profile=out/('profile-'+kind)
            app=P.App(args.candidate.resolve(),args.font.resolve(),profile);app.wait_idle()
            app.wait(lambda:U.IsWindowVisible(app.window))
            if kind=='txt':
                state={identifier:visible(app,identifier) for identifier in (119,126,101,121,122,123,107,109)}
                result['initial_visibility']=state;shot('default-library.bmp')
                assert state[119] and state[126] and not any(state[i] for i in (101,121,122,123,107,109)),state
                record('library-default-minimal')
                menu=U.GetMenu(app.window)
                assert U.GetMenuItemCount(menu)==4
                assert {46001,46002,46003,46004,103,104,105,106,107,108,109,113,114,115,116,117,128,137,170,190,210,260}<=menu_ids(menu)
                record('native-menu-capabilities')
                picker(app);assert send(app.control('books'),0x18B)==0;record('system-picker-cancel-preserves-library')
            picker(app,args.fixtures/filename)
            app.wait(lambda:send(app.control('books'),0x18B)==1,timeout=30)
            record(kind+'-native-import')
            send(app.control('books'),0x186,0);app.click('open');app.wait_idle()
            app.wait(lambda:visible(app,123) and not visible(app,119))
            assert visible(app,46001) and not any(visible(app,i) for i in (101,121,122,107,109))
            assert P.page_number(app.label())>=1
            shot(kind+'-reading.bmp');record(kind+'-reading-view')
            app.close();app=None
        app=P.App(args.candidate.resolve(),args.font.resolve(),out/'profile-txt',existing=True);app.wait_idle()
        app.wait(lambda:visible(app,123))
        first=app.label();app.click('next');app.wait_idle();assert app.label()!=first
        app.click('previous');app.wait_idle();assert app.label()==first;record('reading-next-and-previous')
        app.focus();A.tap(ord('L'),(A.VK_CONTROL,));app.wait(lambda:visible(app,119) and not visible(app,123))
        command(app,46002);assert visible(app,123) and app.label()==first;record('keyboard-library-and-resume')
        command(app,46003);assert all(visible(app,i) for i in (101,119,121,122,123,107,109));record('expanded-panel-retains-controls')
        app.note('Compact native note');app.wait(lambda:send(app.control('notes'),0x18B)>0);record('expanded-panel-note-commit')
        command(app,46003);app.settle((700,480));assert visible(app,123) and not visible(app,122)
        bounds=W.RECT();U.GetClientRect(app.control('page'),C.byref(bounds));assert bounds.right>500 and bounds.bottom>250
        app.focus();app.wait(lambda:A.focus_of(app.process.pid)==app.control('page'))
        shot('small-reading.bmp');record('compact-resize-and-focus')
        command(app,109);app.wait(lambda:visible(app,122))
        bounds=W.RECT();U.GetWindowRect(app.window,C.byref(bounds))
        assert bounds.right-bounds.left>=1060 and bounds.bottom-bounds.top>=660
        record('small-window-note-editor-remains-reachable');command(app,46003)
        for identifier,child,name in ((170,171,'search-native-dialog'),(190,191,'navigation-native-dialog'),
                                       (210,211,'records-native-dialog'),(260,261,'settings-native-dialog')):
            command(app,identifier);dialog=app.wait(lambda:owned_dialog(app,child),timeout=30)
            assert U.IsWindowVisible(dialog)
            U.PostMessageW(dialog,0x10,0,0);app.wait(lambda:not U.IsWindow(dialog),timeout=30)
            app.wait_idle();record(name)
        command(app,46001);assert visible(app,119);app.close();app=None
        app=P.App(args.candidate.resolve(),args.font.resolve(),out/'profile-txt',existing=True);app.wait_idle()
        app.wait(lambda:visible(app,123));assert not visible(app,122);record('restart-restores-compact-reading')
        result.update(accepted=True,count=len(result['checks']))
        validate(result,result['source_sha'],result['run_id'],result['attempt'],result['consumer_sha256'])
    except Exception:
        result['problems'].append(traceback.format_exc());result['accepted']=False;result['count']=len(result['checks'])
    finally:
        if app:app.close()
    result['screenshots']={path.name:dict(bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for path in out.glob('*.bmp')}
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result),flush=True);assert result['accepted']


if __name__=='__main__':main()
