"""Send one real Return only while the expected native window owns focus."""
import ctypes as C
import ctypes.util
import json
import os
import sys


def send_return(window,pid):
    x=C.CDLL(ctypes.util.find_library('X11'))
    xt=C.CDLL(ctypes.util.find_library('Xtst'))
    display=C.c_void_p;word=C.c_ulong
    def signature(lib,name,args,result=C.c_int):
        fn=getattr(lib,name);fn.argtypes=args;fn.restype=result;return fn
    open_display=signature(x,'XOpenDisplay',[C.c_char_p],display)
    close=signature(x,'XCloseDisplay',[display])
    grab=signature(x,'XGrabServer',[display]);ungrab=signature(x,'XUngrabServer',[display])
    sync=signature(x,'XSync',[display,C.c_int])
    focus_get=signature(x,'XGetInputFocus',[display,C.POINTER(word),C.POINTER(C.c_int)])
    atom_get=signature(x,'XInternAtom',[display,C.c_char_p,C.c_int],word)
    property_get=signature(x,'XGetWindowProperty',[display,word,word,C.c_long,C.c_long,C.c_int,word,
        C.POINTER(word),C.POINTER(C.c_int),C.POINTER(word),C.POINTER(word),C.POINTER(C.c_void_p)])
    free=signature(x,'XFree',[C.c_void_p])
    keycode_get=signature(x,'XKeysymToKeycode',[display,word],C.c_ubyte)
    fake=signature(xt,'XTestFakeKeyEvent',[display,C.c_uint,C.c_int,word])
    query_keys=signature(x,'XQueryKeymap',[display,C.c_void_p])
    class Modifiers(C.Structure):
        _fields_=[('max_keypermod',C.c_int),('modifiermap',C.POINTER(C.c_ubyte))]
    modifiers_get=signature(x,'XGetModifierMapping',[display],C.POINTER(Modifiers))
    modifiers_free=signature(x,'XFreeModifiermap',[C.POINTER(Modifiers)])
    d=open_display(None)
    if not d:raise RuntimeError('X display unavailable')
    modifiers=None;data=C.c_void_p();pressed=False;active=[];keycode=0
    try:
        # X11 GrabServer freezes other clients' focus/window requests until
        # our focus check and both XTest key events have been processed.
        # https://www.x.org/docs/XProtocol/proto.pdf (GrabServer/UngrabServer)
        grab(d)
        focus=word();revert=C.c_int();focus_get(d,C.byref(focus),C.byref(revert))
        result={'window':str(window),'pid':pid,'focus':str(focus.value),'sent':False,'mechanism':'XTest-server-grab'}
        if focus.value!=window:return result
        actual_type=word();fmt=C.c_int();count=word();remaining=word()
        status=property_get(d,window,atom_get(d,b'_NET_WM_PID',0),0,1,0,0,
            C.byref(actual_type),C.byref(fmt),C.byref(count),C.byref(remaining),C.byref(data))
        if status or fmt.value!=32 or count.value!=1 or not data or C.cast(data,C.POINTER(word))[0]!=pid:
            raise RuntimeError('Focused import window has wrong owner')
        keycode=keycode_get(d,0xff0d)
        if not keycode:raise RuntimeError('Return keycode unavailable')
        keymap=(C.c_ubyte*32)();query_keys(d,C.byref(keymap))
        modifiers=modifiers_get(d)
        if not modifiers:raise RuntimeError('Modifier map unavailable')
        codes={modifiers.contents.modifiermap[i] for i in range(8*modifiers.contents.max_keypermod)}-{0}
        active=[code for code in codes if keymap[code//8]&(1<<(code%8))]
        for code in active:
            if not fake(d,code,0,0):raise RuntimeError('Cannot clear held modifier')
        if not fake(d,keycode,1,0):raise RuntimeError('Return keydown failed')
        pressed=True
        if not fake(d,keycode,0,0):raise RuntimeError('Return keyup failed')
        pressed=False
        sync(d,0);result['sent']=True
        return result
    finally:
        if pressed:fake(d,keycode,0,0)
        for code in active:fake(d,code,1,0)
        if modifiers:modifiers_free(modifiers)
        if data:free(data)
        ungrab(d);sync(d,0);close(d)


if __name__=='__main__':
    if os.environ.get('GITHUB_ACTIONS')!='true' or not sys.platform.startswith('linux'):
        raise RuntimeError('Linux Actions only')
    print(json.dumps(send_return(int(sys.argv[1]),int(sys.argv[2]))))
