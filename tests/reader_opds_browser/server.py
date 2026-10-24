#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Actions-only fixture service for the reader_opds_browser acceptance run.

Two plain origins and one TLS origin serve OPDS 1 (Atom) and OPDS 2 (JSON) feeds,
pagination chains, facets, OpenSearch and simple acquisition endpoints. Every request
is recorded with the origin and whether an Authorization header arrived, so the check
script can prove credential isolation from the server side.

  python server.py --ready ready.json --log requests.jsonl --fixtures tests/fixtures \
      --cert server.crt --key server.key
"""
import argparse
import io
import json
import ssl
import sys
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

STATE = {"records": [], "lock": threading.Lock(), "bases": {}, "fixtures": "", "log": None}

NS = ('xmlns="http://www.w3.org/2005/Atom" '
      'xmlns:opds="http://opds-spec.org/2010/catalog" '
      'xmlns:thr="http://purl.org/syndication/thread/1.0" '
      'xmlns:dc="http://purl.org/dc/terms/"')

def atom_feed(title, feed_id, links, entries):
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<feed ' + NS + '>\n'
            '  <id>' + feed_id + '</id>\n'
            '  <title>' + title + '</title>\n'
            '  <updated>2026-10-24T00:00:00Z</updated>\n'
            + links + entries + '</feed>\n')

def atom_link(rel, href, mime=None, title=None, extra=""):
    out = '  <link rel="' + rel + '" href="' + href + '"'
    if mime:
        out += ' type="' + mime + '"'
    if title:
        out += ' title="' + title + '"'
    return out + (' ' + extra if extra else '') + '/>\n'

def atom_entry(title, entry_id, extra_children, links):
    return ('  <entry>\n'
            '    <id>' + entry_id + '</id>\n'
            '    <title>' + title + '</title>\n'
            '    <updated>2026-10-24T00:00:00Z</updated>\n'
            + extra_children + links + '  </entry>\n')

def catalog_atom():
    links = (atom_link("self", "/opds1/catalog.xml", "application/atom+xml")
             + atom_link("start", "/opds1/catalog.xml", "application/atom+xml")
             + atom_link("next", "/opds1/page2.xml", "application/atom+xml")
             + atom_link("search", "/opensearch.xml", "application/opensearchdescription+xml")
             + atom_link("http://opds-spec.org/facet", "/opds1/catalog.xml?facet=free", None, "無料",
                         'opds:facetGroup="価格" thr:count="2"')
             + atom_link("http://opds-spec.org/facet", "/opds1/catalog.xml?facet=paid", None, "有料",
                         'opds:facetGroup="価格" opds:activeFacet="true" thr:count="1"')
             + atom_link("http://opds-spec.org/facet", "/opds1/catalog.xml?facet=all", None, "すべて",
                         'opds:facetGroup="価格" thr:count="3"'))
    first_links = (
        atom_link("http://opds-spec.org/acquisition/open-access", "/books/ok.epub", "application/epub+zip", "EPUB")
        + '  <link rel="http://opds-spec.org/acquisition/buy" type="application/pdf" href="/books/ok.pdf">'
          '<opds:price>9.99 USD</opds:price></link>\n'
        + atom_link("http://opds-spec.org/acquisition/borrow", "/books/ok.pdf", "application/pdf")
        + atom_link("http://opds-spec.org/acquisition", "/license.lcp",
                    "application/vnd.readium.lcp.license.v1.0+json")
        + atom_link("http://opds-spec.org/acquisition/sample", "/books/ok.epub", "application/epub+zip")
        + '  <link rel="http://opds-spec.org/acquisition/open-access" type="application/epub+zip" '
          'href="/books/indirect.epub"><opds:indirectAcquisition type="application/epub+zip"/></link>\n'
        + '  <link rel="http://opds-spec.org/acquisition" type="application/epub+zip" href="/books/ok.epub">'
          '<opds:price>4.00 USD</opds:price></link>\n'
        + atom_link("http://opds-spec.org/image/thumbnail", "/cover.png", "image/png"))
    first = atom_entry("日本語の本 — Ünïcode", "urn:uuid:opds1-book-1",
                       '    <author><name>Ada Løvström</name></author>\n'
                       '    <dc:identifier>urn:isbn:9780000000001</dc:identifier>\n'
                       '    <dc:language>ja</dc:language>\n'
                       '    <dc:publisher>青空出版</dc:publisher>\n'
                       '    <summary>要約 — Σύνοψη</summary>\n', first_links)
    second = atom_entry("Plain PDF", "urn:uuid:opds1-book-2",
                        '    <author><name>Second Author</name></author>\n', 
                        atom_link("http://opds-spec.org/acquisition/open-access", "/books/ok.pdf",
                                  "application/pdf"))
    third = atom_entry("Comic CBZ", "urn:uuid:opds1-book-3",
                       '    <author><name>Third Author</name></author>\n',
                       atom_link("http://opds-spec.org/acquisition/open-access", "/books/ok.cbz",
                                 "application/vnd.comicbook+zip"))
    return atom_feed("Fixture OPDS 1 catalogue", "urn:uuid:opds1-feed", links, first + second + third)

def paged_atom(page):
    if page == 2:
        links = (atom_link("self", "/opds1/page2.xml", "application/atom+xml")
                 + atom_link("next", "/opds1/page3.xml", "application/atom+xml"))
        entries = atom_entry("Page two book", "urn:uuid:opds1-p2", "", 
                             atom_link("http://opds-spec.org/acquisition/open-access", "/books/ok.pdf",
                                       "application/pdf"))
    else:
        links = (atom_link("self", "/opds1/page3.xml", "application/atom+xml")
                 + atom_link("next", "/opds1/catalog.xml", "application/atom+xml"))
        entries = atom_entry("Page three book", "urn:uuid:opds1-p3", "",
                             atom_link("http://opds-spec.org/acquisition/open-access", "/books/ok.pdf",
                                       "application/pdf"))
    return atom_feed("Fixture OPDS 1 catalogue", "urn:uuid:opds1-feed", links, entries)

def chain_atom(index):
    links = atom_link("self", "/opds1/chain/%d.xml" % index, "application/atom+xml")
    if index < 5:
        links += atom_link("next", "/opds1/chain/%d.xml" % (index + 1), "application/atom+xml")
    entries = atom_entry("Chain book %d" % index, "urn:uuid:chain-%d" % index, "",
                         atom_link("http://opds-spec.org/acquisition/open-access", "/books/ok.pdf",
                                   "application/pdf"))
    return atom_feed("Chain %d" % index, "urn:uuid:chain", links, entries)

def single_book_atom(feed_id, title, href, mime):
    links = atom_link("self", "/opds1/%s.xml" % feed_id, "application/atom+xml")
    entries = atom_entry(title, "urn:uuid:%s" % feed_id, "",
                         atom_link("http://opds-spec.org/acquisition/open-access", href, mime))
    return atom_feed(title, "urn:uuid:%s" % feed_id, links, entries)

def opensearch():
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<OpenSearchDescription xmlns="http://a9.com/-/spec/opensearch/1.1/">\n'
            '  <ShortName>Fixture</ShortName>\n'
            '  <Url type="application/atom+xml" '
            'template="/opds1/search?q={searchTerms}&amp;page={startPage?}"/>\n'
            '</OpenSearchDescription>\n')

def search_atom(term):
    links = atom_link("self", "/opds1/search", "application/atom+xml")
    entries = atom_entry("結果: " + term, "urn:uuid:search-result", "",
                         atom_link("http://opds-spec.org/acquisition/open-access", "/books/ok.epub",
                                   "application/epub+zip"))
    return atom_feed("検索: " + term, "urn:uuid:search", links, entries)

def catalog_json():
    document = {
        "metadata": {"title": "JSON カタログ"},
        "links": [
            {"rel": "self", "href": "/opds2/catalog.json", "type": "application/opds+json"},
            {"rel": "next", "href": "/opds2/page2.json", "type": "application/opds+json"},
            {"rel": "search", "href": "/opds2/search{?query}", "templated": True,
             "type": "application/atom+xml;profile=opds-catalog"},
        ],
        "navigation": [{"href": "/opds2/nav.json", "title": "部屋", "rel": "subsection"}],
        "publications": [
            {"metadata": {"title": "JSON 本 一", "author": "Renée 作者", "identifier": "urn:uuid:json-1",
                          "language": "ja", "publisher": "JSON 社", "description": "説明",
                          "modified": "2026-10-24T00:00:00Z"},
             "links": [{"rel": "http://opds-spec.org/acquisition/open-access", "href": "/books/ok.epub",
                        "type": "application/epub+zip"}]},
            {"metadata": {"title": "JSON 本 二", "author": "Second JSON", "identifier": "urn:uuid:json-2",
                          "language": "en", "publisher": "JSON 社", "description": "description",
                          "modified": "2026-10-24T00:00:00Z"},
             "links": [{"rel": "http://opds-spec.org/acquisition/open-access", "href": "/books/ok.pdf",
                        "type": "application/pdf"}]},
        ],
        "facets": [{"metadata": {"title": "言語"},
                    "links": [
                        {"href": "/opds2/catalog.json?lang=ja", "title": "日本語",
                         "properties": {"numberOfItems": 2}},
                        {"href": "/opds2/catalog.json?lang=en", "title": "English", "rel": "self",
                         "properties": {"numberOfItems": 1}},
                    ]}],
    }
    return json.dumps(document, ensure_ascii=False).encode("utf-8")

def json_feed(title, publications, links=None):
    document = {"metadata": {"title": title}, "publications": publications}
    if links:
        document["links"] = links
    return json.dumps(document, ensure_ascii=False).encode("utf-8")

def json_publication(title):
    return {"metadata": {"title": title, "author": "JSON author", "identifier": "urn:uuid:" + title,
                         "language": "ja", "modified": "2026-10-24T00:00:00Z"},
            "links": [{"rel": "http://opds-spec.org/acquisition/open-access", "href": "/books/ok.pdf",
                       "type": "application/pdf"}]}

def broken_zip():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, "application/epub+zip")
        archive.writestr("junk.txt", "this container has no META-INF/container.xml")
    return buffer.getvalue()

MINIMAL_PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"

def fixture_bytes(name):
    if name == "ok.epub":
        with open(STATE["fixtures"] + "/sample.epub", "rb") as handle:
            return handle.read(), "application/epub+zip"
    if name == "ok.cbz":
        with open(STATE["fixtures"] + "/comic.cbz", "rb") as handle:
            return handle.read(), "application/vnd.comicbook+zip"
    if name in ("ok.pdf",):
        return MINIMAL_PDF, "application/pdf"
    if name == "fake.epub":
        return b"<!doctype html><html><body>not a book</body></html>\n", "application/epub+zip"
    if name == "fake2.pdf":
        return b"this is not a PDF at all\n", "application/pdf"
    if name in ("broken.epub", "indirect.epub"):
        return broken_zip(), "application/epub+zip"
    return None, None

class Handler(BaseHTTPRequestHandler):
    server_version = "EXReaderOPDSFixture/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def record(self):
        entry = {"origin": self.server.origin, "path": self.path,
                 "authorization": bool(self.headers.get("Authorization"))}
        with STATE["lock"]:
            STATE["records"].append(entry)
            if STATE["log"] is not None:
                STATE["log"].write(json.dumps(entry) + "\n")
                STATE["log"].flush()

    def send_body(self, code, content_type, body, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra or []):
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def send_xml(self, text, code=200):
        self.send_body(code, "application/atom+xml;profile=opds-catalog", text.encode("utf-8"))

    def send_json(self, document, code=200):
        self.send_body(code, "application/json", json.dumps(document, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        self.record()
        parts = urlsplit(self.path)
        path = parts.path
        query = parse_qs(parts.query)
        if path == "/debug/log":
            with STATE["lock"]:
                self.send_json({"records": list(STATE["records"])})
            return
        if path == "/opds1/catalog.xml":
            self.send_xml(catalog_atom())
            return
        if path == "/opds1/page2.xml":
            self.send_xml(paged_atom(2))
            return
        if path == "/opds1/page3.xml":
            self.send_xml(paged_atom(3))
            return
        if path.startswith("/opds1/chain/") and path.endswith(".xml"):
            try:
                index = int(path[len("/opds1/chain/"):-len(".xml")])
            except ValueError:
                self.send_body(404, "text/plain", b"bad chain\n")
                return
            if 1 <= index <= 5:
                self.send_xml(chain_atom(index))
            else:
                self.send_body(404, "text/plain", b"no such chain page\n")
            return
        if path == "/opds1/fake.xml":
            self.send_xml(single_book_atom("fake", "Fake extension", "/books/fake.epub", "application/epub+zip"))
            return
        if path == "/opds1/broken.xml":
            self.send_xml(single_book_atom("broken", "Broken container", "/books/broken.epub",
                                           "application/epub+zip"))
            return
        if path == "/opds1/stall.xml":
            self.send_xml(single_book_atom("stall", "Stalling transfer", "/books/stall.epub",
                                           "application/epub+zip"))
            return
        if path == "/opensearch.xml":
            self.send_body(200, "application/opensearchdescription+xml", opensearch().encode("utf-8"))
            return
        if path == "/opds1/search":
            term = (query.get("q") or [""])[0]
            self.send_xml(search_atom(term))
            return
        if path == "/opds2/catalog.json":
            self.send_body(200, "application/opds+json", catalog_json())
            return
        if path == "/opds2/page2.json":
            self.send_body(200, "application/opds+json",
                           json_feed("JSON page two", [json_publication("JSON page two book")]))
            return
        if path == "/opds2/nav.json":
            self.send_body(200, "application/opds+json",
                           json_feed("JSON navigation", [json_publication("JSON nav book")]))
            return
        if path == "/opds2/search":
            term = (query.get("query") or [""])[0]
            self.send_body(200, "application/opds+json",
                           json_feed("JSON 検索: " + term, [json_publication("JSON search " + term)]))
            return
        if path == "/auth/catalog.xml":
            if (self.headers.get("Authorization") or "") != "Bearer test-token":
                self.send_body(401, "application/atom+xml",
                               b"<feed xmlns=\"http://www.w3.org/2005/Atom\"><title>auth</title></feed>",
                               [("WWW-Authenticate", 'Bearer realm="fixture"')])
                return
            self.send_xml(atom_feed("Authenticated catalogue", "urn:uuid:auth-feed",
                                    atom_link("self", "/auth/catalog.xml", "application/atom+xml"),
                                    atom_entry("Authenticated book", "urn:uuid:auth-book", "",
                                               atom_link("http://opds-spec.org/acquisition/open-access",
                                                         "/books/ok.epub", "application/epub+zip"))))
            return
        if path == "/redirect/to-plain":
            self.send_body(302, "text/plain", b"", [("Location", STATE["bases"]["plain"] + "/opds1/catalog.xml")])
            return
        if path.startswith("/books/"):
            name = path[len("/books/"):]
            if name == "stall.epub":
                self.send_response(200)
                self.send_header("Content-Type", "application/epub+zip")
                self.send_header("Content-Length", "500000")
                self.end_headers()
                self.wfile.write(b"PK\x03\x04" + b"0" * 124)
                self.wfile.flush()
                time.sleep(6)
                return
            body, content_type = fixture_bytes(name)
            if body is None:
                self.send_body(404, "text/plain", b"no such book\n")
                return
            self.send_body(200, content_type, body)
            return
        self.send_body(404, "text/plain", b"no such fixture\n")

class TolerantServer(ThreadingHTTPServer):
    """A stray TCP connect (a port probe) must not kill the TLS accept loop."""

    daemon_threads = True

    def get_request(self):
        while True:
            try:
                return super().get_request()
            except (ssl.SSLError, OSError):
                continue

    def handle_error(self, request, client_address):
        return


def build_server(origin, port, tls, certfile, keyfile):
    httpd = TolerantServer(("127.0.0.1", port), Handler)
    httpd.origin = origin
    httpd.daemon_threads = True
    if tls:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile, keyfile)
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    return httpd

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ready", required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--fixtures", required=True)
    parser.add_argument("--cert", required=True)
    parser.add_argument("--key", required=True)
    arguments = parser.parse_args()
    STATE["fixtures"] = arguments.fixtures
    STATE["log"] = open(arguments.log, "w", encoding="utf-8")
    plain = build_server("plain", 0, False, arguments.cert, arguments.key)
    secure = build_server("tls", 0, True, arguments.cert, arguments.key)
    other = build_server("other", 0, False, arguments.cert, arguments.key)
    STATE["bases"] = {"plain": "http://127.0.0.1:%d" % plain.server_address[1],
                      "tls": "https://127.0.0.1:%d" % secure.server_address[1],
                      "other": "http://127.0.0.1:%d" % other.server_address[1]}
    with open(arguments.ready, "w", encoding="utf-8") as handle:
        json.dump(STATE["bases"], handle)
    for server in (secure, other):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        plain.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0

if __name__ == "__main__":
    sys.exit(main())
