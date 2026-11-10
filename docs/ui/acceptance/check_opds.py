#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""书源 (OPDS) acceptance on the production HWND, against the real Project Gutenberg
catalog (run 1) and a local loopback catalog for the error / cancel / cache cases (run 2).
Screenshots: ops/capture_window.py (via check_selection.launch_capture).
Usage: check_opds.py EXE FONT OUTPUT
"""
import http.server, json, os, sys, threading, time, urllib.parse, zipfile
from pathlib import Path
from check_selection import launch_capture, read, fixture_book

SETUP = 'shell|on\nshell_dpi|96\nshell_client|1280|800\nwait_idle\nshell_click|light\n'
ROOT_URL = 'https://www.gutenberg.org/ebooks.opds/'


def shot(name):
    return f'shell_measure|{name}\nprobe_wait|900\n'


class Local(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, epub):
        super().__init__(('127.0.0.1', 0), Handler)
        self.epub = epub.read_bytes()
        self.hits = {}
        self.lock = threading.Lock()


ATOM = ('<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom">'
        '<title>%s</title>%s%s</feed>')
ACQ = 'http://opds-spec.org/acquisition'


def entry(title, author, body):
    return f'<entry><title>{title}</title><author><name>{author}</name></author>{body}</entry>'


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def send_body(self, status, body, kind):
        self.send_response(status); self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path); path = url.path
        with self.server.lock:
            self.server.hits[path] = self.server.hits.get(path, 0) + 1
        base = f'http://127.0.0.1:{self.server.server_address[1]}'
        atom = 'application/atom+xml;profile=opds-catalog'
        if path == '/feed.xml':
            links = (f'<link rel="next" href="/feed2.xml" type="{atom}"/>'
                     f'<link rel="search" type="{atom}" href="/search?q={{searchTerms}}"/>')
            body = (entry('Local Book', 'Ada Local', f'<summary>Opens from the local feed.</summary><link rel="{ACQ}" type="application/epub+zip" href="/book.epub" length="{len(self.server.epub)}"/>') +
                    entry('Big Book', 'Slow Author', f'<link rel="{ACQ}" type="application/epub+zip" href="/big.epub" length="6291456"/>') +
                    entry('Fake Book', 'Html Page', f'<link rel="{ACQ}" type="application/epub+zip" href="/fake.epub"/>') +
                    entry('Slow Catalog', 'Nobody', f'<link rel="subsection" type="{atom}" href="/slow.xml"/>') +
                    entry('Missing Catalog', 'Nobody', f'<link rel="subsection" type="{atom}" href="/missing.xml"/>'))
            self.send_body(200, (ATOM % ('Local Catalog', links, body)).encode(), atom)
        elif path == '/feed2.xml':
            body = entry('Second Page Book', 'Page Two', f'<link rel="{ACQ}" type="application/epub+zip" href="/book.epub"/>')
            self.send_body(200, (ATOM % ('Local Catalog 2', '', body)).encode(), atom)
        elif path == '/search':
            q = urllib.parse.parse_qs(url.query).get('q', [''])[0]
            body = entry('Result for ' + q, 'Search', f'<link rel="{ACQ}" type="application/epub+zip" href="/book.epub"/>')
            self.send_body(200, (ATOM % ('Search ' + q, '', body)).encode(), atom)
        elif path == '/slow.xml':
            time.sleep(6)
            try: self.send_body(200, (ATOM % ('Slow', '', '')).encode(), atom)
            except OSError: pass
        elif path == '/auth.xml':
            self.send_body(401, b'login required', 'text/plain')
        elif path == '/err500.xml':
            self.send_body(500, b'boom', 'text/plain')
        elif path == '/book.epub':
            self.send_body(200, self.server.epub, 'application/epub+zip')
        elif path == '/fake.epub':
            self.send_body(200, b'<html><body>Not an epub, an error page</body></html>', 'text/html')
        elif path == '/big.epub':
            total = 6 * 1024 * 1024
            self.send_response(200); self.send_header('Content-Type', 'application/epub+zip')
            self.send_header('Content-Length', str(total)); self.end_headers()
            try:
                self.wfile.write(b'PK\x03\x04')
                sent = 4
                while sent < total:
                    n = min(131072, total - sent); self.wfile.write(b'\0' * n); self.wfile.flush(); sent += n
                    time.sleep(.2)
            except OSError:
                pass
        else:
            self.send_body(404, b'not found', 'text/plain')


def last(dump):
    return dump['last']


def main():
    exe, font, out = [Path(x).resolve() for x in sys.argv[1:]]
    out.mkdir(parents=True, exist_ok=True)
    work = out / 'work'; work.mkdir(exist_ok=True)
    epub = work / 'local-book.epub'; fixture_book(epub)
    checks = []

    def check(name, ok, detail):
        checks.append({'check': name, 'pass': bool(ok), 'detail': detail}); print('PASS' if ok else 'FAIL', name, detail)

    # ---------------- run 1: real Project Gutenberg through the window ----------------
    profile = out / 'profile-real'
    s = SETUP + 'opds_show\n' + shot('sources-empty')
    s += f'opds_load|{ROOT_URL}\nopds_dump|root\nopds_open|0\nopds_dump|popular\n' + shot('popular')
    s += 'opds_next\nopds_dump|page2\n' + shot('page2')
    s += 'opds_back\nopds_dump|page1-again\n'
    s += 'opds_open|0\nopds_dump|book\n' + shot('book-editions')
    s += 'opds_download|0\nopds_dump|downloaded\nstate|opened\n' + shot('opened')
    s += 'quit\n'
    launch_capture(exe, font, s, profile, out / 'real', ('sources-empty', 'popular', 'page2', 'book-editions', 'opened'))
    root = read(out / 'real/root.opds.json'); popular = read(out / 'real/popular.opds.json')
    page2 = read(out / 'real/page2.opds.json'); again = read(out / 'real/page1-again.opds.json')
    book = read(out / 'real/book.opds.json'); done = read(out / 'real/downloaded.opds.json')
    opened = None
    for line in (out / 'real/drive.log').read_text(encoding='utf-8').splitlines():
        if '\tstate\t' in line or line.startswith('STEP\tstate'):
            opened = line
    check('ui_root_loaded', root['entries'] > 0 and root['has_search'], f"title={root['title']} entries={root['entries']} search={root['search_template'] or 'description'}")
    check('ui_list_ge_20', popular['entries'] >= 20, f"entries={popular['entries']} first={popular['entries_list'][0]['title']}")
    t1 = [e['title'] for e in popular['entries_list']]; t2 = [e['title'] for e in page2['entries_list']]
    check('ui_next_page_differs', page2['entries'] > 0 and not set(t1) & set(t2), f'page1={len(t1)} page2={len(t2)} overlap={len(set(t1) & set(t2))} page2_first={t2[0]}')
    check('ui_back_uses_cache', again['entries'] == popular['entries'] and again['last']['from_cache'] == 1 and again['cache']['hits'] >= 1, f"entries={again['entries']} from_cache={again['last']['from_cache']} hits={again['cache']['hits']}")
    check('ui_book_has_editions', book['entries'] >= 1 and any(e['format'] == 'epub' for e in book['entries_list']), f"book={t1[0]} editions={[(e['format'], e['size']) for e in book['entries_list']]}")
    d = done['download']
    check('ui_download_ok', d['done'] == 1 and d['file_exists'] and d['file_bytes'] > 10000 and not d['part_file_present'], f"bytes={d['file_bytes']} path={d['path']}")
    check('ui_import_started', d['imports_started'] == 1, 'import_path called once')

    # ---------------- run 1b: restart; the book is on the shelf with metadata/cover ----------------
    s = SETUP + 'sm_show|0\nsm_dump|shelf\nopds_dump|restarted\nquit\n'
    launch_capture(exe, font, s, profile, out / 'real-restart', ())
    shelf = read(out / 'real-restart/shelf.shelf.json')
    entries = shelf['order']
    check('ui_book_on_shelf_after_restart', len(entries) == 1, f"books={len(entries)} title={entries[0]['title'] if entries else ''} author={entries[0]['author'] if entries else ''}")

    # ---------------- run 2: local loopback catalog ----------------
    server = Local(epub); threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_address[1]}'
    profile2 = out / 'profile-local'
    s = SETUP + 'opds_show\n'
    s += f'opds_load|{base}/feed.xml\nopds_dump|local-root\nopds_load|{base}/feed.xml\nopds_dump|local-cached\nopds_refresh\nopds_dump|local-refresh\n'
    s += f'opds_search|dracula\nopds_dump|local-search\nopds_back\n'
    s += f'opds_load|{base}/missing.xml\nopds_dump|err-404\n' + shot('err-404')
    s += 'opds_timeout|1500\n' + f'opds_load|{base}/slow.xml\nopds_dump|err-timeout\n' + shot('err-timeout') + 'opds_timeout|0\n'
    s += f'opds_load|{base}/auth.xml\nopds_dump|err-401\nopds_load|{base}/err500.xml\nopds_dump|err-500\n'
    s += 'opds_load|http://example.com/opds\nopds_dump|err-http\nopds_load|https://no-such-host.invalid/opds\nopds_dump|err-dns\n'
    s += f'opds_load|{base}/feed.xml\nopds_dump|reloaded\n'
    s += 'opds_download|2\nopds_dump|err-fake\n'                     # html page that claims to be an epub
    s += 'opds_download|1|nowait\nopds_sleep|1200\n' + shot('downloading') + 'opds_dump|downloading\nopds_cancel\nopds_wait\nopds_dump|cancelled\n'
    s += 'opds_download|0\nopds_dump|local-downloaded\nstate|local-opened\n' + shot('local-opened') + 'quit\n'
    launch_capture(exe, font, s, profile2, out / 'local', ('err-404', 'err-timeout', 'downloading', 'local-opened'))
    L = {n: read(out / f'local/{n}.opds.json') for n in ('local-root', 'local-cached', 'local-refresh', 'local-search', 'err-404', 'err-timeout',
                                                        'err-401', 'err-500', 'err-http', 'err-dns', 'err-fake', 'downloading', 'cancelled', 'local-downloaded')}
    check('local_feed_loopback', L['local-root']['entries'] == 5 and L['local-root']['has_next'], f"entries={L['local-root']['entries']}")
    check('cache_serves_second_load', L['local-cached']['last']['from_cache'] == 1 and server.hits['/feed.xml'] >= 1, f"from_cache={L['local-cached']['last']['from_cache']}")
    check('refresh_bypasses_cache', L['local-refresh']['last']['from_cache'] == 0, f"server /feed.xml hits={server.hits['/feed.xml']}")
    check('inline_search_template', 'Result for dracula' in [e['title'] for e in L['local-search']['entries_list']], f"template={L['local-search']['search_template']}")
    for name, code, http, needle in (('err-404', 'not_found', 404, '404'), ('err-timeout', 'timeout', 0, '超时'), ('err-401', 'auth', 401, '401'),
                                      ('err-500', 'server_error', 500, '500'), ('err-http', 'not_https', 0, 'HTTPS'), ('err-dns', 'dns', 0, '域名')):
        e = L[name]['last']
        check(f'error_{name[4:]}', e['code'] == code and e['http'] == http and needle in e['message'] and needle in L[name]['status'],
              f"code={e['code']} http={e['http']} message={e['message']} | status={L[name]['status']}")
    check('error_fake_epub_rejected', L['err-fake']['download']['failed'] >= 1 and not L['err-fake']['download']['file_exists'] and '不是有效' in L['err-fake']['status'], L['err-fake']['status'])
    dl = L['downloading']
    check('download_in_progress', dl['busy'] == 1, f"busy={dl['busy']}")
    c = L['cancelled']
    check('download_cancelled', c['download']['cancelled'] == 1 and not c['download']['part_file_present'] and not c['download']['file_exists'] and '已取消' in c['status'],
          f"cancelled={c['download']['cancelled']} part_left={c['download']['part_file_present']} status={c['status']}")
    ld = L['local-downloaded']
    check('local_download_imports', ld['download']['done'] == 1 and ld['download']['imports_started'] == 1, f"shelf={[b['title'] for b in ld['shelf']]}")
    server.shutdown()
    (out / 'result.json').write_text(json.dumps({'checks': checks, 'server_hits': server.hits, 'passed': sum(c['pass'] for c in checks), 'total': len(checks)}, ensure_ascii=False, indent=1), encoding='utf-8')
    failed = [c for c in checks if not c['pass']]
    print(f'{len(checks) - len(failed)}/{len(checks)} checks passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
