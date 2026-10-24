# SPDX-License-Identifier: MIT
"""AT-SPI2 client for the GTK keyboard and accessibility audit.

This module speaks to the real accessibility bus through the platform's
Atspi GObject API.  It reads only what any assistive technology can read: the
exposed name, role, state set, actions, relations, attributes, text and screen
extents, plus the accessibility events the registry delivers.  It never reads
SDK private data, product SQLite tables or application memory.
"""
import re
import threading
import time

import gi

gi.require_version('Atspi', '2.0')
from gi.repository import Atspi, GLib

# States worth recording per element; a member missing on an older
# at-spi2-core is skipped instead of failing the audit.
STATE_NAMES = (
    'ENABLED', 'VISIBLE', 'SHOWING', 'FOCUSED', 'FOCUSABLE', 'SENSITIVE',
    'EDITABLE', 'CHECKED', 'SELECTED', 'SELECTABLE', 'ACTIVE', 'MODAL',
    'EXPANDED', 'MULTI_LINE', 'SINGLE_LINE', 'IS_DEFAULT', 'PRESSED', 'BUSY',
    'READ_ONLY', 'REQUIRED',
)
EVENT_TYPES = (
    'object:property-change',
    'object:state-changed',
    'object:text-changed',
    'object:announcement',
    'focus:',
    'window:',
)


def _safe(call, default=None):
    """Every proxy call can fail when the UI mutates under a walk."""
    try:
        return call()
    except Exception:
        return default


def init():
    """Initialise Atspi; returns (True, '') or (False, diagnostic)."""
    code = _safe(lambda: Atspi.init(), -1)
    if code not in (0, 1):  # 0 = success, 1 = already initialised
        return False, 'Atspi.init() returned %r' % (code,)
    if _safe(lambda: Atspi.get_desktop(0)) is None:
        return False, 'no accessibility desktop'
    return True, ''


def exit_bus():
    _safe(lambda: Atspi.exit())


def role(acc):
    if acc is None:
        return 'unknown'
    found = _safe(lambda: acc.get_role_name())
    if found:
        return str(found).lower()
    value = _safe(lambda: acc.get_role())
    nick = getattr(value, 'value_nick', None)
    return str(nick).replace('-', ' ') if nick else 'unknown'


def name(acc):
    if acc is None:
        return ''
    return str(_safe(lambda: acc.get_name(), '') or '')


def is_defunct(acc):
    state = _safe(lambda: acc.get_state_set())
    if state is None:
        return False
    return bool(_safe(lambda: state.contains(Atspi.StateType.DEFUNCT), False))


def children(acc):
    if acc is None:
        return []
    count = _safe(lambda: acc.get_child_count(), 0) or 0
    out = []
    for index in range(count):
        child = _safe(lambda: acc.get_child_at_index(index))
        if child is not None and not is_defunct(child):
            out.append(child)
    return out


def states(acc):
    state = _safe(lambda: acc.get_state_set()) if acc is not None else None
    if state is None:
        return {}
    out = {}
    for entry in STATE_NAMES:
        kind = getattr(Atspi.StateType, entry, None)
        if kind is None:
            continue
        if _safe(lambda: state.contains(kind), False):
            out[entry.lower()] = True
    return out


def actions(acc):
    iface = _safe(lambda: acc.get_action_iface()) if acc is not None else None
    if iface is None:
        return []
    count = _safe(lambda: iface.get_n_actions(), 0) or 0
    out = []
    for index in range(count):
        out.append({'name': str(_safe(lambda: iface.get_action_name(index), '') or ''),
                    'key_binding': str(_safe(lambda: iface.get_key_binding(index), '') or '')})
    return out


def attributes(acc):
    table = _safe(lambda: acc.get_attributes()) if acc is not None else None
    if table is None:
        return {}
    try:
        return {str(key): str(value) for key, value in table.items()}
    except Exception:
        pass
    out = {}
    for key in _safe(lambda: list(table.keys()), []) or []:
        out[str(key)] = str(_safe(lambda: table.lookup(key), '') or '')
    return out


def relations(acc):
    out = []
    for relation in (_safe(lambda: acc.get_relation_set(), []) if acc is not None else []) or []:
        kind = _safe(lambda: relation.get_relation_type())
        nick = getattr(kind, 'value_nick', None)
        label = str(nick).replace('-', ' ') if nick else str(kind)
        targets = []
        count = _safe(lambda: relation.get_n_targets(), 0) or 0
        for index in range(count):
            target = _safe(lambda: relation.get_target(index))
            if target is not None:
                targets.append({'role': role(target), 'name': name(target)})
        out.append({'type': label, 'targets': targets})
    return out


def extents(acc):
    component = _safe(lambda: acc.get_component_iface()) if acc is not None else None
    if component is None:
        return None
    rect = _safe(lambda: component.get_extents(Atspi.CoordType.SCREEN))
    if rect is None:
        return None
    return {'x': int(rect.x), 'y': int(rect.y), 'width': int(rect.width), 'height': int(rect.height)}


def accessible_text(acc, limit=4096):
    iface = _safe(lambda: acc.get_text_iface()) if acc is not None else None
    if iface is None:
        return None
    count = _safe(lambda: iface.get_character_count(), 0) or 0
    text = _safe(lambda: iface.get_text(0, min(count, limit)), '')
    return {'length': count, 'text': str(text or '')}


def path_of(acc):
    """Stable element path: role[name]#sibling-index, from the desktop root."""
    parts = []
    node = acc
    for _ in range(16):
        if node is None:
            break
        index = 0
        parent = _safe(lambda: node.get_parent())
        if parent is not None:
            for position, sibling in enumerate(children(parent)):
                if same(sibling, node):
                    index = position
                    break
        parts.append('%s[%s]#%d' % (role(node), name(node), index))
        if role(node) == 'application':
            break
        node = parent
    return '/'.join(reversed(parts))


def same(left, right):
    if left is None or right is None:
        return left is right
    return (role(left) == role(right) and name(left) == name(right)
            and extents(left) == extents(right))


def dump(acc, path='', depth=0, max_depth=14):
    node = {'path': path or (role(acc) + '[' + name(acc) + ']'),
            'role': role(acc), 'name': name(acc), 'states': states(acc)}
    found = actions(acc)
    if found:
        node['actions'] = found
    attrs = attributes(acc)
    if attrs:
        node['attributes'] = attrs
    box = extents(acc)
    if box:
        node['extents'] = box
    if depth <= 3:
        relates = relations(acc)
        if relates:
            node['relations'] = relates
    if depth < max_depth:
        node['children'] = []
        for index, child in enumerate(children(acc)):
            child_path = '%s/%s[%s]#%d' % (node['path'], role(child), name(child), index)
            node['children'].append(dump(child, child_path, depth + 1, max_depth))
    return node


def render(node, lines=None, depth=0):
    """Human-readable form of a dump() node."""
    lines = [] if lines is None else lines
    flags = ','.join(sorted(node.get('states', {})))
    acts = ','.join(action['name'] for action in node.get('actions', []))
    attrs = node.get('attributes') or {}
    extra = ''
    if acts:
        extra += ' {' + acts + '}'
    if attrs:
        extra += ' {' + ','.join('%s=%s' % pair for pair in sorted(attrs.items())) + '}'
    lines.append('%s%s "%s" <%s>%s' % ('  ' * depth, node['role'], node['name'], flags, extra))
    for child in node.get('children', []):
        render(child, lines, depth + 1)
    return lines


def walk(acc, depth=0, max_depth=14):
    yield acc
    if depth >= max_depth:
        return
    for child in children(acc):
        for found in walk(child, depth + 1, max_depth):
            yield found


def find_all(acc, roles=None, text=None, contains=None, exact=True):
    out = []
    for node in walk(acc):
        if roles is not None and role(node) not in roles:
            continue
        value = name(node)
        if text is not None:
            if exact and value != text:
                continue
            if not exact and text not in value:
                continue
        if contains is not None and contains not in value:
            continue
        out.append(node)
    return out


def find_one(acc, **criteria):
    found = find_all(acc, **criteria)
    return found[0] if found else None


def applications(desktop=None):
    desktop = desktop if desktop is not None else _safe(lambda: Atspi.get_desktop(0))
    return children(desktop)


def wait_application(pattern, timeout=90):
    """Wait until an application whose name matches pattern registers."""
    regex = re.compile(pattern, re.IGNORECASE)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = [app for app in applications() if regex.search(name(app))]
        if found:
            return found[0]
        time.sleep(0.2)
    raise TimeoutError('application %r did not register on the accessibility bus; registered: %r'
                       % (pattern, [name(app) for app in applications()]))


def is_ancestor(ancestor, node):
    current = _safe(lambda: node.get_parent()) if node is not None else None
    for _ in range(32):
        if current is None:
            return False
        if same(current, ancestor):
            return True
        current = _safe(lambda: current.get_parent())
    return False


def focused_all(acc):
    """Elements that carry FOCUSED and have no focused descendant."""
    focused = [node for node in walk(acc) if states(node).get('focused')]
    return [node for node in focused
            if not any(other is not node and is_ancestor(node, other) for other in focused)]


class Recorder:
    """Collects real accessibility events delivered by at-spi2-registryd."""

    def __init__(self):
        self.items = []
        self.lock = threading.Lock()
        self.listener = None
        self.loop = None
        self.thread = None
        self.registered = []
        self.rejected = []
        self.error = ''

    def _callback(self, event):
        try:
            entry = {'t': round(time.monotonic(), 3),
                     'type': str(getattr(event, 'type', '') or ''),
                     'detail1': str(getattr(event, 'detail1', '') or ''),
                     'detail2': str(getattr(event, 'detail2', '') or '')}
            source = getattr(event, 'source', None)
            if source is not None:
                entry['source_role'] = role(source)
                entry['source_name'] = name(source)
            with self.lock:
                self.items.append(entry)
        except Exception as exc:  # a malformed event must not stop the audit
            with self.lock:
                self.items.append({'t': round(time.monotonic(), 3), 'type': 'callback-error',
                                   'detail1': repr(exc)})

    def start(self, event_types=EVENT_TYPES):
        self.cb = self._callback  # keep the bound callback alive for the listener
        self.listener = _safe(lambda: Atspi.EventListener.new(self.cb))
        if self.listener is None:
            self.error = 'Atspi.EventListener.new() returned None'
            return False
        for entry in event_types:
            ok = False
            try:
                self.listener.register(entry)
                ok = True
            except Exception:
                try:
                    Atspi.EventListener.register(self.listener, entry)
                    ok = True
                except Exception as exc:
                    self.rejected.append({'type': entry, 'error': repr(exc)})
            if ok and entry not in self.registered:
                self.registered.append(entry)
        self.loop = GLib.MainLoop()
        self.thread = threading.Thread(target=self.loop.run, name='atspi-events', daemon=True)
        self.thread.start()
        return bool(self.registered)

    def mark(self):
        with self.lock:
            return len(self.items)

    def since(self, mark):
        with self.lock:
            return list(self.items[mark:])

    def stop(self):
        if self.listener is not None:
            for entry in self.registered:
                _safe(lambda: self.listener.deregister(entry))
        if self.loop is not None:
            _safe(lambda: self.loop.quit())


def atspi_version():
    major = getattr(Atspi, 'MAJOR_VERSION', None)
    minor = getattr(Atspi, 'MINOR_VERSION', None)
    if major is None or minor is None:
        return 'unknown'
    return '%d.%d' % (major, minor)
