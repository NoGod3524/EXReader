#!/usr/bin/env python3
"""Deterministic fault server ONLY. Never evidence of a real desktop service."""
import os
import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
bus = dbus.SessionBus()
class Fixture(dbus.service.Object):
    def __init__(self):
        self.name = dbus.service.BusName('org.gnome.SessionManager', bus=bus)
        self.control = dbus.service.BusName('org.exreader.DisplayFixture', bus=bus)
        super().__init__(bus, '/org/gnome/SessionManager')
        self.mode = 'normal'
        self.cookies = {}
        self.serial = 100
        self.flags = 0
        bus.add_signal_receiver(self.owner_lost, dbus_interface='org.freedesktop.DBus', signal_name='NameOwnerChanged')
    def owner_lost(self, name, old, new):
        if old and not new:
            self.cookies = {k:v for k,v in self.cookies.items() if v != old}
    @dbus.service.method('org.gnome.SessionManager', in_signature='susu', out_signature='u', sender_keyword='sender', async_callbacks=('ok','err'))
    def Inhibit(self, app, xid, reason, flags, sender=None, ok=None, err=None):
        self.flags = int(flags)
        if self.mode == 'denied':
            err(dbus.exceptions.DBusException('denied', name='org.freedesktop.DBus.Error.AccessDenied')); return
        if self.mode == 'zero':
            ok(dbus.UInt32(0)); return
        self.serial += 1
        cookie = self.serial
        self.cookies[cookie] = sender
        def reply():
            ok(dbus.UInt32(cookie)); return False
        delay = {'late':600, 'timeout':3000}.get(self.mode, 0)
        if delay: GLib.timeout_add(delay, reply)
        else: reply()
    @dbus.service.method('org.gnome.SessionManager', in_signature='u', out_signature='', sender_keyword='sender')
    def Uninhibit(self, cookie, sender=None):
        if self.cookies.get(int(cookie)) == sender:
            del self.cookies[int(cookie)]
    @dbus.service.method('org.exreader.DisplayFixture', in_signature='s', out_signature='')
    def Mode(self, mode): self.mode = str(mode)
    @dbus.service.method('org.exreader.DisplayFixture', in_signature='', out_signature='u')
    def Count(self): return dbus.UInt32(len(self.cookies))
    @dbus.service.method('org.exreader.DisplayFixture', in_signature='', out_signature='u')
    def Flags(self): return dbus.UInt32(self.flags)
    @dbus.service.method('org.exreader.DisplayFixture', in_signature='', out_signature='')
    def Drop(self):
        self.cookies.clear()
        self.name = None
        bus.release_name('org.gnome.SessionManager')
    @dbus.service.method('org.exreader.DisplayFixture', in_signature='', out_signature='')
    def Grab(self): self.name = dbus.service.BusName('org.gnome.SessionManager', bus=bus)
f = Fixture()
print('FIXTURE_READY', flush=True)
GLib.MainLoop().run()
