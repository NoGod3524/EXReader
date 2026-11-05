"""Read-only Xlib geometry: distinguish actual client, WM frame and root spaces.

xdotool getwindowgeometry on a reparented window included doubled frame offsets
on this runner. Never use that value as a screen-coordinate reference.
"""
import ctypes as c
lib=c.CDLL('libX11.so.6')
W=c.c_ulong;I=c.c_int;U=c.c_uint;D=c.c_void_p
lib.XOpenDisplay.argtypes=[c.c_char_p];lib.XOpenDisplay.restype=D
lib.XCloseDisplay.argtypes=[D]
lib.XQueryTree.argtypes=[D,W,c.POINTER(W),c.POINTER(W),c.POINTER(c.POINTER(W)),c.POINTER(U)]
lib.XGetGeometry.argtypes=[D,W,c.POINTER(W),c.POINTER(I),c.POINTER(I),c.POINTER(U),c.POINTER(U),c.POINTER(U),c.POINTER(U)]
lib.XTranslateCoordinates.argtypes=[D,W,W,I,I,c.POINTER(I),c.POINTER(I),c.POINTER(W)]
lib.XFree.argtypes=[D]
def geometry(window):
    display=lib.XOpenDisplay(None)
    if not display:raise RuntimeError('Cannot open actual X display')
    try:
        current=int(window);chain=[];root=W()
        for _ in range(12):
            parent=W();children=c.POINTER(W)();count=U()
            assert lib.XQueryTree(display,current,c.byref(root),c.byref(parent),c.byref(children),c.byref(count))
            if children:lib.XFree(children)
            chain.append(current)
            if parent.value==root.value:break
            current=parent.value
        else:raise AssertionError('WM frame ancestor not found')
        def box(xid):
            x=I();y=I();width=U();height=U();border=U();depth=U();foundroot=W();child=W();rx=I();ry=I()
            assert lib.XGetGeometry(display,xid,c.byref(foundroot),c.byref(x),c.byref(y),c.byref(width),c.byref(height),c.byref(border),c.byref(depth))
            assert lib.XTranslateCoordinates(display,xid,root.value,0,0,c.byref(rx),c.byref(ry),c.byref(child))
            return dict(WINDOW=xid,X=rx.value,Y=ry.value,WIDTH=width.value,HEIGHT=height.value,BORDER=border.value,DEPTH=depth.value)
        return dict(client=box(int(window)),frame=box(current),root=box(root.value),ancestor_chain=chain)
    finally:lib.XCloseDisplay(display)
