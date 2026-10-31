#!/usr/bin/env python3
"""Fixed local OPDS test service (GitHub runner only). Two origins: A (main) and B (foreign).

usage: server.py --corpus DIR --fixtures DIR --log FILE --ports FILE [--basic VALUE] [--bearer VALUE]

Writes {"a": port, "b": port} to --ports once both listen, then serves until killed.
The request log never records header or query *values* of credentials: only
method, path, the names of the query keys and auth state none|ok|bad.
"""
import argparse
import json
import os
import struct
import sys
import threading
import time
import urllib.parse
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from xml.sax.saxutils import escape, quoteattr

ATOM_NS = ('xmlns="http://www.w3.org/2005/Atom" xmlns:opds="http://opds-spec.org/2010/catalog" '
           'xmlns:os="http://a9.com/-/spec/opensearch/1.1/" xmlns:dc="http://purl.org/dc/terms/"')
ATOM_CT = "application/atom+xml;profile=opds-catalog;kind=navigation"
OPDS2_CT = "application/opds+json"
BOOKS = [("Alpha Story", "Ann Author"), ("Beta Story", "Ben Writer"), ("Gamma Story", "Gus 作者"),
         ("Delta Notes", "Dee Editor"), ("Epsilon Tale", "Eve Eliot")]
PAGE = 2
LOG_LOCK = threading.Lock()
CFG = {}


def log_request(server, method, path, query, auth):
    row = {"server": server, "method": method, "path": path,
           "query_keys": sorted(urllib.parse.parse_qs(query, keep_blank_values=True).keys()), "auth": auth}
    with LOG_LOCK:
        with open(CFG["log"], "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def crafted_corrupt_epub():
    name, data = b"mimetype", b"application/epub+zip"
    hdr = struct.pack("<4sHHHHHIIIHH", b"PK\x03\x04", 20, 0, 0, 0, 0, zlib.crc32(data), len(data), len(data), len(name), 0)
    return hdr + name + data + b"garbage-without-central-directory" * 40


def book_atom(i, title, author):
    t = escape(title)
    href = "/dl/gamma%20story.epub" if i == 2 else "/dl/book.epub"
    return (f'<entry><title>{t}</title><id>urn:opds-test:{i}</id><updated>2026-01-01T00:00:00Z</updated>'
            f'<author><name>{escape(author)}</name></author><dc:identifier>urn:opds-test:isbn:{i}</dc:identifier>'
            f'<link rel="http://opds-spec.org/acquisition/open-access" href="{href}" type="application/epub+zip"/>'
            f'<link rel="http://opds-spec.org/image/thumbnail" href="/img/{i}.png" type="image/png"/></entry>')


def atom_page(title, selfhref, books, page, last, extra_links=""):
    links = [f'<link rel="self" href={quoteattr(selfhref)} type="{ATOM_CT}"/>']
    pat = selfhref.split("?")[0]
    q = ""
    if "q=" in selfhref:
        q = "&" + [p for p in selfhref.split("?")[1].split("&") if p.startswith("q=")][0]
    links.append(f'<link rel="first" href={quoteattr(pat.rsplit("/", 1)[1] + "?page=1" + q)} type="{ATOM_CT}"/>')
    links.append(f'<link rel="last" href={quoteattr(pat.rsplit("/", 1)[1] + "?page=" + str(last) + q)} type="{ATOM_CT}"/>')
    if page > 1:
        links.append(f'<link rel="previous" href={quoteattr(pat.rsplit("/", 1)[1] + "?page=" + str(page - 1) + q)} type="{ATOM_CT}"/>')
    if page < last:
        links.append(f'<link rel="next" href={quoteattr(pat.rsplit("/", 1)[1] + "?page=" + str(page + 1) + q)} type="{ATOM_CT}"/>')
    ents = "".join(book_atom(i, t, a) for i, t, a in books)
    return (f'<?xml version="1.0" encoding="utf-8"?><feed {ATOM_NS}><title>{escape(title)}</title><id>urn:opds-test:feed</id>'
            f'<updated>2026-01-01T00:00:00Z</updated>{"".join(links)}{extra_links}{ents}</feed>')


def select_books(q):
    out = [(i, t, a) for i, (t, a) in enumerate(BOOKS) if not q or q.casefold() in t.casefold()]
    return out


def pub_json(i, title, author):
    href = "/dl/gamma%20story.epub" if i == 2 else "/dl/book.epub"
    return {"metadata": {"title": title, "identifier": f"urn:opds-test:{i}", "author": [{"name": author}], "language": ["en"]},
            "links": [{"rel": "http://opds-spec.org/acquisition/open-access", "href": href, "type": "application/epub+zip"}],
            "images": [{"href": f"/img/{i}.png", "type": "image/png"}]}


def json_page(title, name, books, page, last, q=None):
    suffix = f"&q={urllib.parse.quote(q)}" if q else ""
    links = [{"rel": "self", "href": f"{name}?page={page}{suffix}", "type": OPDS2_CT},
             {"rel": "first", "href": f"{name}?page=1{suffix}", "type": OPDS2_CT},
             {"rel": "last", "href": f"{name}?page={last}{suffix}", "type": OPDS2_CT}]
    if page > 1:
        links.append({"rel": "previous", "href": f"{name}?page={page - 1}{suffix}", "type": OPDS2_CT})
    if page < last:
        links.append({"rel": "next", "href": f"{name}?page={page + 1}{suffix}", "type": OPDS2_CT})
    return {"metadata": {"title": title, "numberOfItems": 0, "itemsPerPage": PAGE, "currentPage": page},
            "links": links, "publications": [pub_json(*b) for b in books]}


def loop_atom(page):
    other = 2 if page == 1 else 1
    return (f'<?xml version="1.0"?><feed {ATOM_NS}><title>Loop {page}</title><id>urn:loop:{page}</id>'
            f'<link rel="next" href="loop?page={other}" type="{ATOM_CT}"/>'
            f'<entry><title>Entry {page}</title><id>urn:loop:e{page}</id><link rel="subsection" href="x" type="{ATOM_CT}"/></entry></feed>')


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_label = "A"

    def log_message(self, fmt, *args):
        pass

    # ---- helpers ----
    def auth_state(self):
        got = self.headers.get("Authorization")
        if got is None:
            return "none"
        return "ok" if got in (CFG.get("basic"), CFG.get("bearer")) else "bad"

    def send(self, status, body=b"", ctype="text/plain", headers=None, length=True):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        if length:
            self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Connection", "close")
        self.end_headers()
        if body:
            self.wfile.write(body)
        self.close_connection = True

    def redirect(self, loc, status=302):
        self.send(status, b"", "text/plain", {"Location": loc})

    def need_auth(self, scheme):
        self.send(401, "auth required", "text/plain", {"WWW-Authenticate": f'{scheme} realm="fixture"'})

    def fixture(self, name):
        with open(os.path.join(CFG["fixtures"], name), "rb") as f:
            return f.read()

    def corpus(self, rel):
        with open(os.path.join(CFG["corpus"], rel), "rb") as f:
            return f.read()

    def chunked(self, ctype, pieces, status=200):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("Connection", "close")
        self.end_headers()
        for p in pieces:
            self.wfile.write(f"{len(p):x}\r\n".encode() + p + b"\r\n")
        self.wfile.write(b"0\r\n\r\n")
        self.close_connection = True

    # ---- routing ----
    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        path, query = urllib.parse.unquote(u.path), u.query
        qs = urllib.parse.parse_qs(query)
        state = self.auth_state()
        log_request(self.server_label, "GET", u.path, query, state)
        try:
            if self.server_label == "B":
                return self.route_b(path, qs, state)
            return self.route_a(path, qs, state)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def route_b(self, path, qs, state):
        if path == "/b/auth/root.xml":
            if state != "ok":
                return self.need_auth("Basic")
            return self.send(200, self.corpus("o1/root.xml"), ATOM_CT)
        if path == "/b/public/root.xml":
            return self.send(200, self.corpus("o1/root.xml"), ATOM_CT)
        if path == "/b/public/book.epub":
            return self.send(200, self.fixture("layout.epub"), "application/epub+zip")
        return self.send(404, "not found")

    def route_a(self, path, qs, state):
        if path.startswith("/c/"):
            rel = path[3:]
            if ".." in rel:
                return self.send(400, "bad path")
            try:
                body = self.corpus(rel)
            except OSError:
                return self.send(404, "not found")
            ctype = {"xml": ATOM_CT, "json": OPDS2_CT, "html": "text/html"}.get(rel.rsplit(".", 1)[-1], "application/octet-stream")
            if "ctype" in qs:
                ctype = qs["ctype"][0]
            return self.send(200, body, ctype)
        if path.startswith("/auth/"):
            scheme = "Bearer" if "/o2/" in path else "Basic"
            if state != "ok":
                return self.need_auth(scheme)
            if path == "/auth/o1/root.xml":
                return self.send(200, self.corpus("o1/root.xml"), ATOM_CT)
            if path == "/auth/o2/root.json":
                return self.send(200, self.corpus("o2/root.json"), OPDS2_CT)
            if path == "/auth/dl/book.epub":
                return self.send(200, self.fixture("layout.epub"), "application/epub+zip")
            return self.send(404, "not found")
        if path == "/o1/all" or path == "/o1/search":
            q = qs.get("q", [""])[0] if path.endswith("search") else ""
            page = int(qs.get("page", ["1"])[0])
            books = select_books(q)
            last = max(1, (len(books) + PAGE - 1) // PAGE)
            sel = f"{path}?page={page}" + (f"&q={urllib.parse.quote(q)}" if path.endswith("search") else "")
            title = f"Results for: {q}" if path.endswith("search") else "All books"
            return self.send(200, atom_page(title, sel, books[(page - 1) * PAGE:page * PAGE], page, last), ATOM_CT)
        if path == "/o1/search2":
            q = qs.get("query", [""])[0]
            books = select_books(q)
            return self.send(200, atom_page(f"Direct results for: {q}", "/o1/search2?page=1", books[:PAGE], 1, 1), ATOM_CT)
        if path == "/o1/opensearch.xml":
            return self.send(200, self.corpus("o1/opensearch.xml"), "application/opensearchdescription+xml")
        if path == "/o1/loop":
            return self.send(200, loop_atom(int(qs.get("page", ["1"])[0])), ATOM_CT)
        if path == "/o2/all" or path == "/o2/search":
            q = qs.get("q", qs.get("query", [""]))[0] if path.endswith("search") else ""
            page = int(qs.get("page", ["1"])[0])
            books = select_books(q)
            last = max(1, (len(books) + PAGE - 1) // PAGE)
            name = path.rsplit("/", 1)[1]
            doc = json_page(f"Results for: {q}" if q else "All books", name, books[(page - 1) * PAGE:page * PAGE], page, last,
                            q if path.endswith("search") else None)
            doc["metadata"]["numberOfItems"] = len(books)
            return self.send(200, json.dumps(doc, ensure_ascii=False), OPDS2_CT)
        if path == "/o2/loop":
            page = int(qs.get("page", ["1"])[0])
            other = 2 if page == 1 else 1
            doc = {"metadata": {"title": f"Loop {page}"}, "links": [{"rel": "next", "href": f"loop?page={other}", "type": OPDS2_CT}],
                   "navigation": [{"title": "x", "href": "x", "type": OPDS2_CT}]}
            return self.send(200, json.dumps(doc), OPDS2_CT)
        if path.startswith("/gen/"):
            return self.generated(path, qs)
        if path.startswith("/r/"):
            return self.redirects(path, qs)
        if path == "/slow/feed.xml":
            time.sleep(int(qs.get("delay", ["2000"])[0]) / 1000.0)
            return self.send(200, self.corpus("o1/root.xml"), ATOM_CT)
        if path == "/chunked/feed.xml":
            body = self.corpus("o1/root.xml")
            return self.chunked(ATOM_CT, [body[i:i + 97] for i in range(0, len(body), 97)])
        if path == "/trunc/feed.xml":
            body = self.corpus("o1/root.xml")
            self.send_response(200)
            self.send_header("Content-Type", ATOM_CT)
            self.send_header("Content-Length", str(len(body) + 5000))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body[:200])
            self.close_connection = True
            return
        if path == "/huge-length/feed.xml":
            self.send_response(200)
            self.send_header("Content-Type", ATOM_CT)
            self.send_header("Content-Length", str(50 * 1024 * 1024))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(b"<feed")
            self.close_connection = True
            return
        if path == "/status/404":
            return self.send(404, "gone")
        if path == "/status/500":
            return self.send(500, "boom")
        if path == "/status/403":
            return self.send(403, "forbidden")
        if path.startswith("/dl/"):
            return self.downloads(path, qs)
        if path.startswith("/img/"):
            return self.send(200, b"\x89PNG\r\n\x1a\n", "image/png")
        return self.send(404, "not found")

    def generated(self, path, qs):
        n = int(qs.get("n", ["10"])[0])
        if path == "/gen/o1/entries":
            ents = "".join(f'<entry><title>Book {i}</title><id>urn:gen:{i}</id></entry>' for i in range(n))
            return self.send(200, f'<feed {ATOM_NS}><title>Many</title><id>urn:gen</id>{ents}</feed>', ATOM_CT)
        if path == "/gen/o1/deep":
            return self.send(200, f'<feed {ATOM_NS}><title>Deep</title>' + "<x>" * n + "</x>" * n + "</feed>", ATOM_CT)
        if path == "/gen/o1/bytes":
            return self.send(200, f'<feed {ATOM_NS}><title>Big</title><id>urn:big</id><summary>' + "a" * n + "</summary></feed>", ATOM_CT)
        if path == "/gen/o1/links":
            links = "".join(f'<link rel="related" href="/l/{i}"/>' for i in range(n))
            return self.send(200, f'<feed {ATOM_NS}><title>L</title><id>urn:l</id><entry><title>E</title><id>urn:e</id>{links}</entry></feed>', ATOM_CT)
        if path == "/gen/o2/entries":
            doc = {"metadata": {"title": "Many"}, "publications": [{"metadata": {"title": f"Book {i}"}, "links": []} for i in range(n)]}
            return self.send(200, json.dumps(doc), OPDS2_CT)
        if path == "/gen/o2/deep":
            return self.send(200, '{"metadata":{"title":"Deep"},"links":[],"x":' + "[" * n + "]" * n + "}", OPDS2_CT)
        if path == "/gen/o2/bytes":
            return self.send(200, json.dumps({"metadata": {"title": "Big"}, "links": [], "pad": "a" * n}), OPDS2_CT)
        return self.send(404, "not found")

    def redirects(self, path, qs):
        if path == "/r/chain":
            n = int(qs.get("n", ["0"])[0])
            if n > 0:
                return self.redirect(f"/r/chain?n={n - 1}", 301 if n % 2 else 302)
            return self.send(200, self.corpus("o1/root.xml"), ATOM_CT)
        if path == "/r/loop/a":
            return self.redirect("/r/loop/b")
        if path == "/r/loop/b":
            return self.redirect("/r/loop/a")
        if path == "/r/ftp":
            return self.redirect("ftp://example.invalid/feed")
        if path == "/r/nolocation":
            return self.send(302, "")
        if path == "/r/xorigin":
            return self.redirect(qs["to"][0])
        if path == "/r/same-auth":
            return self.redirect("/auth/o1/root.xml")
        if path == "/r/dl":
            return self.redirect("/dl/book.epub")
        return self.send(404, "not found")

    def downloads(self, path, qs):
        name = path[4:]
        epub = self.fixture("layout.epub")
        if name in ("book.epub", "gamma story.epub"):
            return self.send(200, epub, "application/epub+zip")
        if name == "book.pdf":
            return self.send(200, self.fixture("pdf-public.pdf"), "application/pdf")
        if name == "html-as-epub.epub":
            return self.send(200, "<!DOCTYPE html><html><body>Please sign in</body></html>", "application/epub+zip")
        if name == "pdf-as-epub.epub":
            return self.send(200, self.fixture("pdf-public.pdf"), "application/epub+zip")
        if name == "plain-type.epub":
            return self.send(200, epub, "text/plain")
        if name == "corrupt.epub":
            return self.send(200, crafted_corrupt_epub(), "application/epub+zip")
        if name == "empty.epub":
            return self.send(200, b"", "application/epub+zip")
        if name == "different.epub":
            # a distinct but valid-looking payload: the same EPUB with a trailing comment area
            return self.send(200, epub + b"\0" * 32, "application/epub+zip")
        if name == "trunc.epub":
            self.send_response(200)
            self.send_header("Content-Type", "application/epub+zip")
            self.send_header("Content-Length", str(len(epub)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(epub[: len(epub) // 2])
            self.close_connection = True
            return
        if name == "slow.epub":
            self.send_response(200)
            self.send_header("Content-Type", "application/epub+zip")
            self.send_header("Content-Length", str(len(epub)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(epub[:2048])
            self.wfile.flush()
            time.sleep(int(qs.get("stall", ["4000"])[0]) / 1000.0)
            self.wfile.write(epub[2048:])
            self.close_connection = True
            return
        if name == "stream.bin":
            return self.chunked("application/octet-stream", [b"\0" * 8192 for _ in range(40)])
        return self.send(404, "not found")


class ThreadedServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--fixtures", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--ports", required=True)
    ap.add_argument("--basic")
    ap.add_argument("--bearer")
    a = ap.parse_args()
    CFG.update(corpus=a.corpus, fixtures=a.fixtures, log=a.log, basic=a.basic, bearer=a.bearer)
    open(a.log, "w").close()

    class HA(Handler):
        server_label = "A"

    class HB(Handler):
        server_label = "B"

    sa = ThreadedServer(("127.0.0.1", 0), HA)
    sb = ThreadedServer(("127.0.0.1", 0), HB)
    for s in (sa, sb):
        threading.Thread(target=s.serve_forever, daemon=True).start()
    with open(a.ports, "w") as f:
        json.dump({"a": sa.server_address[1], "b": sb.server_address[1]}, f)
    print("opds test server ready", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
