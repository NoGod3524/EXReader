#!/usr/bin/env python3
"""Read-only byte survey of the pinned RTF streams (CI evidence, not a parser).

It reports the facts the SDK's rejection rules depend on, so the root cause of
an EXR_FORMAT result is named from the real bytes instead of guessed: group
balance and what follows the root group, NUL bytes, numeric parameter range,
\\bin lengths, \\u range, \\' escapes, code page and control-word vocabulary.
The SDK parser stays the only RTF parser used by the product and the tests.
"""
import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

INT_MAX = 2**31 - 1


def survey(data):
    n = len(data)
    out = {"bytes": n, "sha256": hashlib.sha256(data).hexdigest(), "head": data[:48].decode("latin-1")}
    out["nul"] = {"count": data.count(0), "first": [i for i in range(n) if data[i] == 0][:8]}
    words = collections.Counter()
    big = []            # parameters beyond int32
    bins = []
    ucodes = {"out_of_range": [], "count": 0}
    bad_hex = []
    codepages = []
    depth = max_depth = 0
    root_end = None
    first_unbalanced = None
    i = 0
    while i < n:
        c = data[i]
        i += 1
        if c == 0x7B:
            depth += 1
            max_depth = max(max_depth, depth)
        elif c == 0x7D:
            depth -= 1
            if depth == 0 and root_end is None:
                root_end = i
            if depth < 0 and first_unbalanced is None:
                first_unbalanced = i - 1
        elif c == 0x5C and i < n:
            d = data[i]
            if chr(d).isalpha() and d < 128:
                j = i
                while j < n and chr(data[j]).isalpha() and data[j] < 128:
                    j += 1
                word = data[i:j].decode("ascii")
                neg = j < n and data[j] == 0x2D
                k = j + 1 if neg else j
                m = k
                while m < n and 0x30 <= data[m] <= 0x39:
                    m += 1
                has = m > k
                value = int(data[k:m]) * (-1 if neg else 1) if has else None
                words[word] += 1
                if has and (value > INT_MAX or value < -INT_MAX - 1):
                    big.append({"word": word, "value": value, "offset": i})
                if word == "ansicpg" and has:
                    codepages.append(value)
                if word == "u" and has:
                    ucodes["count"] += 1
                    if value < -32768 or value > 65535:
                        ucodes["out_of_range"].append({"value": value, "offset": i})
                end = m + 1 if m < n and data[m] == 0x20 else m
                if word == "bin":
                    length = value if has else None
                    ok = has and 0 <= length <= n - end
                    bins.append({"offset": i, "length": length, "remaining": n - end, "fits": bool(ok)})
                    if ok:
                        end += length
                i = end
            elif d == 0x27:
                hexdigits = data[i + 1:i + 3]
                if len(hexdigits) < 2 or any(b not in b"0123456789abcdefABCDEF" for b in hexdigits):
                    bad_hex.append(i)
                i += 3
            else:
                i += 1
    out["groups"] = {"final_depth": depth, "max_depth": max_depth, "root_end": root_end,
                     "first_unbalanced": first_unbalanced}
    if root_end is not None:
        tail = data[root_end:]
        out["tail_after_root"] = {
            "bytes": len(tail),
            "hex_head": tail[:32].hex(),
            "only_nul": bool(tail) and set(tail) == {0},
            "only_nul_or_whitespace": all(b in b"\x00\r\n \t" for b in tail),
            "first_non_padding": next((root_end + k for k, b in enumerate(tail) if b not in b"\x00\r\n \t"), None),
        }
    out["parameters_beyond_int32"] = big[:20]
    out["bin"] = bins[:20]
    out["unicode"] = ucodes
    out["bad_hex_escapes"] = bad_hex[:20]
    out["ansicpg"] = sorted(set(codepages))
    out["distinct_words"] = len(words)
    out["words_top"] = words.most_common(40)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    report = {"schema": 1, "files": {Path(f).name: survey(Path(f).read_bytes()) for f in args.files}}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
