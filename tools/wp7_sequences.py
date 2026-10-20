#!/usr/bin/env python3
"""Fixed WP7 shaping corpus: 50 distinct sequences for each supported script.

The sequences are original combinations of Unicode scalars.  They exercise
independent vowels, dependent vowel signs in every reordering class, consonant
conjuncts, reph/raker/kinzi, joiners, marks, digits and word contexts.  The
same list is used for the real Noto fonts and the original synthetic fonts.
"""
# SPDX-License-Identifier: MIT

INDIC = {
    "beng": dict(
        virama=0x09CD, ra=0x09B0,
        cons=[0x0995,0x0996,0x0997,0x099A,0x099C,0x099F,0x09A4,0x09A6,0x09A8,0x09AA,
              0x09AE,0x09AF,0x09B0,0x09B2,0x09B6,0x09B7,0x09B8,0x09B9],
        ind=[0x0985,0x0986,0x0987,0x0988,0x0989,0x098A,0x098B,0x098F,0x0990,0x0993,0x0994],
        mat=[0x09BE,0x09BF,0x09C0,0x09C1,0x09C2,0x09C3,0x09C7,0x09C8,0x09CB,0x09CC,0x09D7],
        marks=[0x0981,0x0982,0x0983,0x09BC], digits=list(range(0x09E6,0x09F0))),
    "taml": dict(
        virama=0x0BCD, ra=0x0BB0,
        cons=[0x0B95,0x0B99,0x0B9A,0x0B9C,0x0B9F,0x0BA4,0x0BA8,0x0BAA,0x0BAE,0x0BAF,
              0x0BB0,0x0BB2,0x0BB3,0x0BB4,0x0BB5,0x0BB6,0x0BB7,0x0BB8,0x0BB9],
        ind=[0x0B85,0x0B86,0x0B87,0x0B88,0x0B89,0x0B8A,0x0B8E,0x0B8F,0x0B90,0x0B92,0x0B93,0x0B94],
        mat=[0x0BBE,0x0BBF,0x0BC0,0x0BC1,0x0BC2,0x0BC6,0x0BC7,0x0BC8,0x0BCA,0x0BCB,0x0BCC],
        marks=[0x0B82,0x0B83,0x0BD7], digits=list(range(0x0BE6,0x0BEF))),
    "telu": dict(
        virama=0x0C4D, ra=0x0C30,
        cons=[0x0C15,0x0C16,0x0C17,0x0C1A,0x0C1C,0x0C1F,0x0C24,0x0C26,0x0C28,0x0C2A,
              0x0C2E,0x0C2F,0x0C30,0x0C32,0x0C36,0x0C37,0x0C38,0x0C39],
        ind=[0x0C05,0x0C06,0x0C07,0x0C08,0x0C09,0x0C0A,0x0C0B,0x0C0E,0x0C0F,0x0C10,0x0C12,0x0C13,0x0C14],
        mat=[0x0C3E,0x0C3F,0x0C40,0x0C41,0x0C42,0x0C46,0x0C47,0x0C48,0x0C4A,0x0C4B,0x0C4C],
        marks=[0x0C00,0x0C01,0x0C02,0x0C03,0x0C3C,0x0C55,0x0C56], digits=list(range(0x0C66,0x0C70))),
    "knda": dict(
        virama=0x0CCD, ra=0x0CB0,
        cons=[0x0C95,0x0C96,0x0C97,0x0C9A,0x0C9C,0x0C9F,0x0CA4,0x0CA6,0x0CA8,0x0CAA,
              0x0CAE,0x0CAF,0x0CB0,0x0CB2,0x0CB6,0x0CB7,0x0CB8,0x0CB9],
        ind=[0x0C85,0x0C86,0x0C87,0x0C88,0x0C89,0x0C8A,0x0C8E,0x0C8F,0x0C90,0x0C92,0x0C93,0x0C94],
        mat=[0x0CBE,0x0CBF,0x0CC0,0x0CC1,0x0CC2,0x0CC6,0x0CC7,0x0CC8,0x0CCA,0x0CCB,0x0CCC],
        marks=[0x0C80,0x0C81,0x0C82,0x0C83,0x0CBC], digits=list(range(0x0CE6,0x0CEF))),
    "mlym": dict(
        virama=0x0D4D, ra=0x0D30,
        cons=[0x0D15,0x0D16,0x0D17,0x0D1A,0x0D1C,0x0D1F,0x0D24,0x0D26,0x0D28,0x0D2A,
              0x0D2E,0x0D2F,0x0D30,0x0D32,0x0D36,0x0D37,0x0D38,0x0D39],
        ind=[0x0D05,0x0D06,0x0D07,0x0D08,0x0D09,0x0D0A,0x0D0E,0x0D0F,0x0D10,0x0D12,0x0D13,0x0D14],
        mat=[0x0D3E,0x0D3F,0x0D40,0x0D41,0x0D42,0x0D46,0x0D47,0x0D48,0x0D4A,0x0D4B,0x0D4C],
        marks=[0x0D00,0x0D01,0x0D02,0x0D03,0x0D3C], digits=list(range(0x0D66,0x0D70))),
}

THAI_C = [0x0E01,0x0E02,0x0E04,0x0E07,0x0E10,0x0E14,0x0E17,0x0E19,0x0E1B,0x0E1D,
          0x0E1F,0x0E20,0x0E22,0x0E23,0x0E25,0x0E27,0x0E2A,0x0E2B,0x0E2C,0x0E2D]
THAI_M = [0x0E30,0x0E31,0x0E32,0x0E33,0x0E34,0x0E35,0x0E36,0x0E37,0x0E38,0x0E39,
          0x0E3A,0x0E40,0x0E41,0x0E42,0x0E43,0x0E44,0x0E47,0x0E48,0x0E49,0x0E4A,
          0x0E4B,0x0E4C,0x0E4D,0x0E4E]
KHMER_C = [0x1780,0x1781,0x1782,0x1784,0x1786,0x1789,0x178A,0x178B,0x178E,0x1790,
           0x1791,0x1793,0x1794,0x1795,0x1796,0x1797,0x1798,0x179A,0x179B,0x179C,
           0x179D,0x179E,0x17A0,0x17A2]
KHMER_M = [0x17B6,0x17B7,0x17B8,0x17B9,0x17BA,0x17BB,0x17BC,0x17BD,0x17BE,0x17BF,
           0x17C0,0x17C1,0x17C2,0x17C3,0x17C4,0x17C5,0x17C6,0x17C7,0x17C8,0x17C9,
           0x17CA,0x17CB,0x17CC,0x17CD,0x17CE,0x17D0,0x17D1,0x17D3]
MYANMAR_C = [0x1000,0x1001,0x1002,0x1004,0x1005,0x1006,0x1007,0x1009,0x100A,0x100B,
             0x100F,0x1010,0x1011,0x1012,0x1013,0x1014,0x1015,0x1016,0x1017,0x1018,
             0x1019,0x101A,0x101B,0x101C,0x101E,0x1020,0x1021]
MYANMAR_M = [0x102B,0x102C,0x102D,0x102E,0x102F,0x1030,0x1031,0x1032,0x1033,0x1034,
             0x1035,0x1036,0x1037,0x1038,0x103B,0x103C,0x103D,0x103E,0x103A,0x1039]


def indic_cases(tag):
    v = INDIC[tag]
    c, m, out = v["cons"], v["mat"], []
    out.extend(chr(cp) for cp in v["ind"][:11])
    out.append(chr(v["ind"][0]) + chr(v["marks"][1]))
    out.extend(chr(c[i % len(c)]) + chr(cp) for i, cp in enumerate(m[:11]))
    out.extend(chr(c[i]) + chr(v["virama"]) + chr(c[(i + 5) % len(c)]) for i in range(10))
    out += [
        chr(v["ra"]) + chr(v["virama"]) + chr(c[0]),
        chr(v["ra"]) + chr(v["virama"]) + chr(c[0]) + chr(m[1]),
        chr(v["ra"]) + chr(v["virama"]) + chr(c[1]),
        chr(c[0]) + chr(v["virama"]) + chr(v["ra"]),
        chr(c[0]) + chr(v["virama"]) + chr(c[1]) + chr(v["virama"]) + chr(c[2]),
        chr(c[0]) + chr(v["virama"]) + chr(v["ra"]) + chr(v["virama"]) + chr(c[0]),
        chr(c[0]) + chr(v["marks"][0]),
        chr(c[0]) + chr(v["marks"][1]),
        chr(c[0]) + chr(v["marks"][2]),
        chr(c[0]) + chr(v["virama"]) + chr(0x200D) + chr(c[1]),
        chr(c[0]) + chr(v["virama"]) + chr(0x200C) + chr(c[1]),
        chr(c[0]) + chr(v["virama"]) + chr(0x200D),
        chr(c[0]) + chr(v["virama"]) + chr(0x200C),
        chr(c[0]) + chr(m[1]) + " " + chr(c[1]) + chr(m[2]),
        "".join(chr(x) for x in v["digits"][:4]),
        chr(c[0]) + chr(m[0]) + "," + chr(c[1]) + chr(m[1]),
        chr(v["virama"]) + chr(c[2]),
    ]
    return out[:50]


def thai_cases():
    out = [chr(cp) for cp in THAI_C[:12]]
    out += [chr(THAI_C[i % 12]) + chr(cp) for i, cp in enumerate(THAI_M[:14])]
    out += [chr(THAI_C[i]) + chr(THAI_M[(i + 4) % len(THAI_M)]) + chr(THAI_M[(i + 16) % len(THAI_M)])
            for i in range(8)]
    out += ["\u0e14\u0e33", "\u0e14\u0e4b\u0e33", "\u0e01\u0e33", "\u0e01\u0e4d\u0e32",
            "\u0e01\u0e34\u0e49", "\u0e01\u0e49\u0e34", "\u0e2a\u0e27\u0e31\u0e2a\u0e14\u0e35",
            "\u0e20\u0e32\u0e29\u0e32\u0e44\u0e17\u0e22", "\u0e01\u0e23\u0e30\u0e17\u0e39\u0e49",
            "\u0e1b\u0e23\u0e30\u0e40\u0e17\u0e28\u0e44\u0e17\u0e22", "\u0e51\u0e52\u0e53\u0e54",
            "\u0e01\u0e34\u0e48\u0e07", "\u0e01\u0e33\u0e25\u0e31\u0e07", "\u0e40\u0e01\u0e47\u0e07",
            "\u0e2b\u0e19\u0e31\u0e07\u0e2a\u0e37\u0e2d", "\u0e01\u0e32\u0e23\u0e2d\u0e48\u0e32\u0e19",
            "\u0e20\u0e39\u0e40\u0e02\u0e32", "\u0e19\u0e49\u0e33", "\u0e44\u0e17\u0e22"]
    return out[:50]


def khmer_cases():
    out = [chr(cp) for cp in KHMER_C[:12]]
    out += [chr(KHMER_C[i % 12]) + chr(cp) for i, cp in enumerate(KHMER_M[:14])]
    out += [chr(KHMER_C[i]) + "\u17d2" + chr(KHMER_C[(i + 6) % len(KHMER_C)]) for i in range(10)]
    out += [chr(KHMER_C[i]) + "\u17d2\u179a" for i in range(4)]
    out += [chr(KHMER_C[i]) + "\u17d2\u179a" + chr(KHMER_M[i]) for i in range(4)]
    out += [chr(KHMER_C[i]) + "\u17d2" + chr(KHMER_C[(i + 3) % len(KHMER_C)]) + chr(KHMER_M[(i + 8) % len(KHMER_M)]) for i in range(4)]
    out += ["\u1781\u17d2\u1798\u17c2\u179a", "\u1797\u17b6\u179f\u17b6\u1781\u17d2\u1798\u17c2\u179a",
            "\u1780\u17d2\u1798\u17bb\u17c6", "\u179f\u17d2\u179a\u17b8\u17a2\u17d2\u1793\u17bb\u1782",
            "\u1780\u17c6\u1796\u17bb\u1787\u17b6", "\u17e1\u17e2\u17e3\u17e4",
            "\u1780\u17b6\u179a\u17ad\u17b6\u1793", "\u1798\u17b6\u1793\u17c1\u17d2\u1799"]
    return out[:50]


def myanmar_cases():
    out = [chr(cp) for cp in MYANMAR_C[:12]]
    out += [chr(MYANMAR_C[i % 12]) + chr(cp) for i, cp in enumerate(MYANMAR_M[:14])]
    out += [chr(MYANMAR_C[i]) + "\u1039" + chr(MYANMAR_C[(i + 5) % len(MYANMAR_C)]) for i in range(8)]
    out += [chr(0x1004) + "\u103a\u1039" + chr(MYANMAR_C[i]) for i in range(4)]
    out += [chr(MYANMAR_C[i]) + "\u103b" for i in range(4)]
    out += [chr(MYANMAR_C[i]) + "\u103c" for i in range(4)]
    out += [chr(MYANMAR_C[i]) + "\u103d" for i in range(4)]
    out += ["\u1019\u103c\u1014\u103a\u1019\u102c", "\u1019\u103c\u1014\u103a\u1019\u102c\u1015\u103a",
            "\u1000\u103c\u100a\u103a\u1019\u103a", "\u101e\u1004\u103a\u1039\u1000\u103c\u102e",
            "\u1019\u102d\u1014\u103a\u101e\u102c", "\u1041\u1042\u1043\u1044",
            "\u1000\u102c\u101c\u102c\u1019\u1015\u103a", "\u1010\u1030\u101b\u103e\u102c"]
    return out[:50]


CASES = {
    "beng": indic_cases("beng"), "taml": indic_cases("taml"), "telu": indic_cases("telu"),
    "knda": indic_cases("knda"), "mlym": indic_cases("mlym"), "thai": thai_cases(),
    "khmr": khmer_cases(), "mymr": myanmar_cases(),
}

if __name__ == "__main__":
    import json
    import sys
    for tag, values in CASES.items():
        assert len(values) == 50 and len(set(values)) == 50, tag
        print(tag, len(values))
    if len(sys.argv) == 2:
        open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(CASES, ensure_ascii=False))
