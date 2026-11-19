#!/usr/bin/env bash
# Acceptance batch for the final DLL. Run from the repository root while holding the bench lock.
set -e
E=evidence/dense-vector-residual-20261119; W=$E/harness; D=$E/_work/dlls; F=tests/fixtures
hb() { pwsh -NoProfile -File /c/Users/Oscar/OneDrive/Desktop/deepseekHarness/ops/bench-lock.ps1 -Holder opus-densevec2 -Heartbeat > /dev/null; }
mkdir -p $E/paired
python -B -u $W/ab.py $D/base.dll $D/base-copy.dll $E/control-1200.json --rounds 21
python -B -u $W/ab.py $D/base.dll $D/final.dll $E/dense-1200.json --rounds 21
python -B -u $W/ab.py $D/base.dll $D/final.dll $E/dense-vs-pdfjs-1200.json --rounds 15 --pdfjs-root ../pdfjs-bench2
for n in vector-heavy-100 real-mixed-120 image-heavy-100; do
  last=$([ $n = real-mixed-120 ] && echo 120 || echo 100)
  python -B -u $W/ab.py $D/base.dll $D/final.dll $E/paired/$n-1200.json --rounds 11 --pdf $F/pdf-large/$n.pdf --first 1 --last $last
done
for cell in "pdf-hybrid-real/pptx-20.pdf 600 20" "pdf-hybrid-real/pptx-20.pdf 1200 20" "pdf-ppt/deck.pdf 1200 15" "pdf-hybrid-real/word-5.pdf 1200 5"; do
  set -- $cell; hb
  python -B -u $W/ab.py $D/base.dll $D/final.dll $E/paired/$(basename $1 .pdf)-$2.json --rounds 15 --pdf $F/$1 --first 1 --last $3 --width $2
done
hb; python -B -u $W/pixels.py $D/base.dll $D/final.dll $E/pixels.json
hb; python -B -u $W/rss.py $D/base.dll $D/final.dll $E/rss.json
hb; ctest --test-dir build/perf --parallel 4 --output-on-failure > $E/ctest.txt 2>&1 || true
tail -3 $E/ctest.txt
echo ACCEPT-DONE
