#!/usr/bin/env bash
# Pilot pairs on image-heavy-100 p71-100 @1200. Run from the repository root.
set -e
E=evidence/image-p71-100-composite-20261119; D=$E/_work/dlls; AB=evidence/dense-vector-residual-20261119/harness/ab.py
LOCK=/c/Users/Oscar/OneDrive/Desktop/deepseekHarness/ops/bench-lock.ps1
export EXR_IDLE_GATE=off
pwsh -NoProfile -File $LOCK -Holder opus-A -Wait
trap 'pwsh -NoProfile -File $LOCK -Holder opus-A -Release' EXIT
PDF="--pdf tests/fixtures/pdf-large/image-heavy-100.pdf --first 71 --last 100 --holder opus-A"
python -B -u $AB $D/relink-base.dll $D/relink-base-copy.dll $E/pilot/control.json --rounds 15 $PDF
python -B -u $AB $D/relink-base.dll $D/cand-site4.dll $E/pilot/site4.json --rounds 15 $PDF
python -B -u $AB $D/relink-base.dll $D/cand-site3.dll $E/pilot/site3.json --rounds 15 $PDF
python -B -u $AB $D/relink-base.dll $D/cand-both.dll $E/pilot/both.json --rounds 15 $PDF
echo PILOT-DONE
