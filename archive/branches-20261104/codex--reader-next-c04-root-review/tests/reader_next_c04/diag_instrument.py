#!/usr/bin/env python3
"""Make a diagnostic-only copy of src/rtf.c that names where exr_rtf gave up.

Every `goto done;` inside exr_rtf reports source line, stream offset, depth and
the bytes just consumed on stderr before jumping. The copy is built only in the
separate diagnostic job; it is never the candidate and never installed as the SDK.
"""
import re
import sys
from pathlib import Path

HELPER = r'''
#include <stdio.h>
static void rtf_diag(const unsigned char *s, size_t n, size_t i, size_t depth, int line, int status) {
  size_t from = i > 48 ? i - 48 : 0, to = i + 16 < n ? i + 16 : n, k;
  fprintf(stderr, "RTF-FAIL c-line=%d status=%d offset=%zu of %zu depth=%zu\n  before:", line, status, i, n, depth);
  for (k = from; k < to; k++) fprintf(stderr, k == i ? "|%02x" : " %02x", s[k]);
  fprintf(stderr, "\n  text:  ");
  for (k = from; k < to; k++) fputc(s[k] >= 32 && s[k] < 127 ? s[k] : '.', stderr);
  fprintf(stderr, "\n");
}
'''


def main():
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    text = src.read_text(encoding="utf-8")
    at = text.index("exr_status exr_rtf(")
    head, body = text[:at], text[at:]
    body, count = re.subn(r"goto done;",
                          "{ rtf_diag(s,n,i,depth,__LINE__,(int)context.status); goto done; }", body)
    assert count > 10, count
    dst.write_text(head + HELPER + body, encoding="utf-8", newline="\n")
    print("instrumented %d exits" % count)


if __name__ == "__main__":
    main()
