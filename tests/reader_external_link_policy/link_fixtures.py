#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fixed expectations for the external link policy consumers.

The expected outcomes are written down here, from the contract in
docs/READER-EXTERNAL-LINK-POLICY.md, before any consumer reads the fixture.
They are never produced by running the library.
"""
from pathlib import Path

ACTION = {"REJECT": 0, "INTERNAL": 1, "NEEDS_HOST": 2}
REASON = {name: i for i, name in enumerate((
    "NONE", "EMPTY", "TOO_LONG", "INVALID_UTF8", "CONTROL", "SPACE", "BACKSLASH", "BAD_ESCAPE",
    "ENCODED_CONTROL", "ENCODED_SEPARATOR", "ENCODED_DOT", "DOUBLE_ESCAPE", "FORBIDDEN_SCHEME",
    "UNKNOWN_SCHEME", "BAD_SCHEME", "PROTOCOL_RELATIVE", "ABSOLUTE_PATH", "PATH_ESCAPE",
    "BAD_AUTHORITY", "USERINFO", "BAD_PATH_CHAR", "MALFORMED"))}
KIND = {"NONE": 0, "FRAGMENT": 1, "CFI": 2, "CONTAINER_PATH": 3, "EXTERNAL": 4}
UNSAFE, NON_ASCII, HAS_FRAGMENT = 1, 2, 4
BASE = b"OEBPS/text/ch1.xhtml"
DEFAULT_LIMIT = 8192
CUSTOM_LIMIT = 64

# Groups that must be present (with at least this many cases) in every fixture run.
REQUIRED_GROUPS = {
    "external-allowed": 6, "mixed-case-scheme": 3, "unicode": 6, "userinfo": 3,
    "protocol-relative": 2, "encoded-separators": 4, "double-escape": 2, "path-escape": 4,
    "forbidden-scheme": 8, "unknown-scheme": 3, "bad-scheme": 5, "controls": 6,
    "invalid-utf8": 3, "overlong": 6, "authority": 8, "internal-allowed": 12,
    "fragment-and-cfi": 6, "escapes": 6, "spaces": 3,
}


def _frag(data):
    if b"#" in data:
        i = data.index(b"#")
        return HAS_FRAGMENT, i + 1, len(data) - i - 1
    return 0, 0, 0


def _case(group, name, data, base, action, reason, kind, scheme, path_len, flags, off, flen):
    return {"name": group + "/" + name, "group": group, "base": base, "input": data,
            "action": action, "reason": reason, "kind": kind, "path_len": path_len,
            "frag_off": off, "frag_len": flen, "flags": flags, "scheme": scheme}


def host(group, name, text, scheme, extra_flags=0):
    data = text if isinstance(text, bytes) else text.encode("utf-8")
    flags, off, flen = _frag(data)
    return _case(group, name, data, None, "NEEDS_HOST", "NONE", "EXTERNAL", scheme, 0,
                 flags | extra_flags, off, flen)


def internal(group, name, text, kind, base=BASE):
    data = text if isinstance(text, bytes) else text.encode("utf-8")
    flags, off, flen = _frag(data)
    path_len = data.index(b"#") if b"#" in data else len(data)
    if data.startswith(b"#"):
        path_len = 0
    return _case(group, name, data, base, "INTERNAL", "NONE", kind, "", path_len, flags, off, flen)


def reject(group, name, text, reason, unsafe=False, base=BASE):
    data = text if isinstance(text, bytes) else text.encode("utf-8")
    return _case(group, name, data, base, "REJECT", reason, "NONE", "", 0,
                 UNSAFE if unsafe else 0, 0, 0)


def default_cases():
    c = []
    for n, t in (("https", "https://example.com/a?b=1#frag"), ("http-port", "http://example.com:8080/x"),
                 ("mailto", "mailto:reader@example.com?subject=hi%20there"),
                 ("ipv6", "http://[2001:db8::1]:8080/"), ("trailing-dot", "https://example.com./"),
                 ("fragment-no-path", "https://example.com#top"),
                 ("encoded-crlf-in-query", "mailto:a@example.com?body=x%0D%0Ay")):
        c.append(host("external-allowed", n, t, t.split(":", 1)[0]))
    c.append(host("mixed-case-scheme", "https", "HtTpS://Example.COM/Path", "https"))
    c.append(host("mixed-case-scheme", "mailto", "MAILTO:A@Example.com", "mailto"))
    c.append(host("mixed-case-scheme", "http", "hTTp://example.com/", "http"))
    c.append(host("unicode", "path", "https://example.com/路径/文件?q=é", "https"))
    c.append(host("unicode", "idn-host", "https://例え.jp/", "https", NON_ASCII))
    c.append(host("unicode", "fragment", "https://example.com/#章节", "https"))
    c.append(internal("unicode", "cjk-path", "章节/第一章.xhtml", "CONTAINER_PATH"))
    c.append(internal("unicode", "encoded-utf8", "%E7%AB%A0.xhtml", "CONTAINER_PATH"))
    c.append(reject("unicode", "fullwidth-scheme", "ｊavascript:alert(1)", "BAD_SCHEME"))
    c.append(reject("unicode", "bidi-override", "https://example.com/\u202eexe.txt", "CONTROL", True))
    c.append(reject("unicode", "line-separator", "ch2\u2028.xhtml", "CONTROL", True))
    for n, t in (("password", "https://user:pw@example.com/"), ("lookalike", "https://example.com@evil.example/"),
                 ("empty-userinfo", "http://@example.com/")):
        c.append(reject("userinfo", n, t, "USERINFO"))
    c.append(reject("protocol-relative", "host", "//example.com/x", "PROTOCOL_RELATIVE"))
    c.append(reject("protocol-relative", "triple", "///x", "PROTOCOL_RELATIVE"))
    c.append(reject("protocol-relative", "absolute", "/OEBPS/x.xhtml", "ABSOLUTE_PATH"))
    for n, t in (("slash", "a%2Fb.xhtml"), ("backslash-upper", "a%5Cb.xhtml"), ("backslash-lower", "a%5cb.xhtml"),
                 ("lower-hex", "a%2fb.xhtml")):
        c.append(reject("encoded-separators", n, t, "ENCODED_SEPARATOR"))
    c.append(reject("double-escape", "encoded-dot-dot", "a%252e%252e/b", "DOUBLE_ESCAPE"))
    c.append(reject("double-escape", "encoded-slash", "a%252Fb", "DOUBLE_ESCAPE"))
    c.append(internal("double-escape", "literal-percent-allowed", "a%25zz.xhtml", "CONTAINER_PATH"))
    c.append(reject("path-escape", "three-up", "../../../x.xhtml", "PATH_ESCAPE"))
    c.append(reject("path-escape", "root-up", "../x", "PATH_ESCAPE", base=None))
    c.append(reject("path-escape", "down-then-up", "a/../../x", "PATH_ESCAPE", base=b"ch1.xhtml"))
    c.append(reject("path-escape", "encoded-dot-dot", "%2e%2e/x.xhtml", "ENCODED_DOT"))
    c.append(reject("path-escape", "mixed-dot", ".%2e/x", "ENCODED_DOT"))
    c.append(reject("path-escape", "encoded-dot", "%2E/x", "ENCODED_DOT"))
    c.append(reject("path-escape", "empty-resolution", ".", "MALFORMED", base=b"ch1.xhtml"))
    c.append(reject("path-escape", "cancelling-dots", "a/..", "MALFORMED", base=b"ch1.xhtml"))
    for n, t in (("javascript", "javascript:alert(1)"), ("mixed-javascript", "JaVaScRiPt:alert(1)"),
                 ("data", "data:text/html;base64,AAAA"), ("vbscript", "vbscript:msgbox"),
                 ("file", "file:///etc/passwd"), ("drive-letter", "C:/Windows/System32/cmd.exe"),
                 ("ms-protocol", "ms-msdt:/id"), ("ms-mixed", "MS-Settings:x"), ("search-ms", "search-ms:query=x"),
                 ("cmd", "cmd:/c")):
        c.append(reject("forbidden-scheme", n, t, "FORBIDDEN_SCHEME"))
    for n, t in (("ftp", "ftp://example.com/"), ("tel-default", "tel:+15551234"), ("unknown", "foo-bar:baz")):
        c.append(reject("unknown-scheme", n, t, "UNKNOWN_SCHEME"))
    c.append(reject("bad-scheme", "percent-scheme", "java%73cript:alert(1)", "BAD_SCHEME"))
    c.append(reject("bad-scheme", "digit-first", "1http://x", "BAD_SCHEME"))
    c.append(reject("bad-scheme", "empty-scheme", ":foo", "BAD_SCHEME"))
    c.append(reject("bad-scheme", "too-long-scheme", "abcdefghijklmnopq:x", "BAD_SCHEME"))
    c.append(reject("bad-scheme", "unicode-scheme", "章节:1.xhtml", "BAD_SCHEME"))
    c.append(reject("controls", "tab-in-scheme", "java\tscript:x", "CONTROL", True))
    c.append(reject("controls", "nul", b"https://example.com/\x00x", "CONTROL", True))
    c.append(reject("controls", "newline", b"https://example.com/\nx", "CONTROL", True))
    c.append(reject("controls", "del", b"ch2\x7f.xhtml", "CONTROL", True))
    c.append(reject("controls", "c1", "ch2\u0085.xhtml", "CONTROL", True))
    c.append(reject("controls", "nbsp", "ch2\u00a0.xhtml", "CONTROL", True))
    c.append(reject("invalid-utf8", "lone-continuation", b"https://example.com/\xff", "INVALID_UTF8", True))
    c.append(reject("invalid-utf8", "truncated", b"https://example.com/\xe2\x82", "INVALID_UTF8", True))
    c.append(reject("invalid-utf8", "overlong", b"https://example.com/\xc0\xaf", "INVALID_UTF8", True))
    c.append(reject("spaces", "leading", " javascript:x", "SPACE"))
    c.append(reject("spaces", "trailing", "https://example.com/ ", "SPACE"))
    c.append(reject("spaces", "inside-external", "https://exa mple.com/", "SPACE"))
    c.append(internal("spaces", "inside-internal", "my file.xhtml", "CONTAINER_PATH"))
    c.append(internal("spaces", "escaped", "my%20file.xhtml", "CONTAINER_PATH"))
    c.append(reject("overlong", "empty", b"", "EMPTY"))
    c.append(reject("overlong", "external-8193", b"https://example.com/" + b"a" * (8193 - 20), "TOO_LONG"))
    c.append(host("overlong", "external-8192", b"https://example.com/" + b"a" * (8192 - 20), "https"))
    c.append(reject("overlong", "path-2048", b"a" * 2048, "TOO_LONG", base=None))
    c.append(internal("overlong", "path-2047", b"a" * 2047, "CONTAINER_PATH", base=None))
    c.append(reject("overlong", "fragment-2048", b"#" + b"a" * 2048, "TOO_LONG"))
    c.append(internal("overlong", "fragment-2047", b"#" + b"a" * 2047, "FRAGMENT"))
    c.append(reject("overlong", "segments-257", b"/".join([b"a"] * 257), "TOO_LONG", base=None))
    c.append(internal("overlong", "segments-256", b"/".join([b"a"] * 256), "CONTAINER_PATH", base=None))
    for n, t, a in (("no-colon-host", "https://", "BAD_AUTHORITY"), ("empty-host", "https:///x", "BAD_AUTHORITY"),
                    ("port-only", "https://:80/", "BAD_AUTHORITY"), ("encoded-host", "https://exa%6dple.com/", "BAD_AUTHORITY"),
                    ("port-range", "https://example.com:99999/", "BAD_AUTHORITY"),
                    ("port-letters", "https://example.com:80a/", "BAD_AUTHORITY"),
                    ("empty-label", "https://ex..ample.com/", "BAD_AUTHORITY"),
                    ("open-bracket", "https://[::1/", "BAD_AUTHORITY"),
                    ("no-slashes", "https:example.com", "MALFORMED"), ("scheme-only", "https:", "MALFORMED")):
        c.append(reject("authority", n, t, a))
    for n, t, k in (("fragment", "#note1", "FRAGMENT"), ("empty-fragment", "#", "FRAGMENT"),
                    ("sibling", "ch2.xhtml", "CONTAINER_PATH"), ("sibling-fragment", "ch2.xhtml#sec-1", "CONTAINER_PATH"),
                    ("parent", "../images/a.png", "CONTAINER_PATH"), ("dot-slash", "./ch2.xhtml", "CONTAINER_PATH"),
                    ("up-and-down", "../../x.xhtml", "CONTAINER_PATH"),
                    ("cfi-in-document", "#epubcfi(/6/4[chap01ref]!/4[body01]/10[para05]/3:10)", "CFI"),
                    ("cfi-with-path", "ch2.xhtml#epubcfi(/4/2)", "CFI")):
        c.append(internal("internal-allowed", n, t, k))
    c.append(internal("internal-allowed", "root-base", "ch1.xhtml", "CONTAINER_PATH", base=None))
    c.append(internal("internal-allowed", "root-base-empty-string", "text/ch2.xhtml", "CONTAINER_PATH", base=b""))
    c.append(internal("internal-allowed", "deep", "a/b/c/d.xhtml", "CONTAINER_PATH"))
    c.append(internal("internal-allowed", "pct-fragment", "#id%20x", "FRAGMENT"))
    c.append(internal("fragment-and-cfi", "frag", "#a", "FRAGMENT"))
    c.append(internal("fragment-and-cfi", "cfi", "#epubcfi(/4/2)", "CFI"))
    c.append(reject("fragment-and-cfi", "double-hash", "#a#b", "MALFORMED"))
    c.append(reject("fragment-and-cfi", "cfi-short", "#epubcfi(", "MALFORMED"))
    c.append(reject("fragment-and-cfi", "cfi-open", "#epubcfi(/4/2", "MALFORMED"))
    c.append(reject("fragment-and-cfi", "external-double-hash", "https://example.com/#a#b", "MALFORMED"))
    for n, t, r in (("bad-hex", "a%zz", "BAD_ESCAPE"), ("short", "a%4", "BAD_ESCAPE"),
                    ("invalid-utf8", "a%FF.xhtml", "BAD_ESCAPE"), ("bidi", "%E2%80%AE.xhtml", "ENCODED_CONTROL"),
                    ("nul", "a%00b", "ENCODED_CONTROL"), ("newline", "a%0Ab", "ENCODED_CONTROL"),
                    ("colon", "a%3Ab", "BAD_PATH_CHAR"), ("raw-colon", "./a:b", "BAD_PATH_CHAR"),
                    ("query", "a?b=1", "BAD_PATH_CHAR"), ("leading-query", "?x", "BAD_PATH_CHAR"),
                    ("backslash", "a\\b", "BACKSLASH"), ("fragment-bad-hex", "#a%zz", "BAD_ESCAPE"),
                    ("fragment-nul", "#a%00", "ENCODED_CONTROL")):
        c.append(reject("escapes", n, t, r, unsafe=False))
    c.append(reject("escapes", "external-bad-hex", "https://example.com/%zz", "BAD_ESCAPE"))
    c.append(reject("escapes", "external-nul", "https://example.com/%00", "ENCODED_CONTROL"))
    c.append(reject("escapes", "external-backslash", "https://example.com/x\\y", "BACKSLASH"))
    c.append(host("escapes", "external-double-escape-allowed", "https://example.com/a%2520b", "https"))
    c.append(host("escapes", "external-encoded-slash-allowed", "https://example.com/a%2Fb", "https"))
    return c


def custom_cases():
    """Policy with extra schemes tel and geo and max_input_bytes = 64."""
    c = [host("custom", "tel", "tel:+15551234", "tel"), host("custom", "tel-upper", "TEL:+1555", "tel"),
         host("custom", "geo", "geo:48.2,16.3", "geo"), reject("custom", "sms", "sms:123", "UNKNOWN_SCHEME"),
         reject("custom", "denied-still", "javascript:x", "FORBIDDEN_SCHEME"),
         reject("custom", "over-64", b"https://example.com/" + b"a" * 45, "TOO_LONG"),
         host("custom", "exactly-64", b"https://example.com/" + b"a" * 44, "https")]
    return c


CUSTOM_HEADER = "#schemes tel,geo\n#max 64\n"


def encode(cases, header=""):
    lines = []
    for case in cases:
        base = "-" if case["base"] is None else (case["base"].hex() or ".")
        lines.append("\t".join((
            case["name"], base, case["input"].hex() or ".", str(ACTION[case["action"]]),
            str(REASON[case["reason"]]), str(KIND[case["kind"]]), str(case["path_len"]),
            str(case["frag_off"]), str(case["frag_len"]), str(case["flags"]), case["scheme"] or "-")))
    return header + "\n".join(lines) + "\n"


def write(directory):
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    names = set()
    for cases, name, header in ((default_cases(), "default.tsv", ""), (custom_cases(), "custom.tsv", CUSTOM_HEADER)):
        for case in cases:
            assert case["name"] not in names, case["name"]
            names.add(case["name"])
        (out / name).write_text(encode(cases, header), encoding="utf-8", newline="\n")
    counts = {}
    for case in default_cases():
        counts[case["group"]] = counts.get(case["group"], 0) + 1
    for group, minimum in REQUIRED_GROUPS.items():
        assert counts.get(group, 0) >= minimum, (group, counts.get(group, 0), minimum)
    return len(default_cases()), len(custom_cases())
