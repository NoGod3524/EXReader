#!/usr/bin/env bash
# Batch 1: p1-21 absolute time + same-DLL empty control, then the stage probe.
# Run from the repository root. Takes and releases the global bench lock.
set -e
E=evidence/realmixed-gradient-mask-20261119; D=$E/_work/dlls
LOCK=/c/Users/Oscar/OneDrive/Desktop/deepseekHarness/ops/bench-lock.ps1
export EXR_IDLE_GATE=off
mkdir -p $E/raw
pwsh -NoProfile -File $LOCK -Holder agy-C -Wait
trap 'pwsh -NoProfile -File $LOCK -Holder agy-C -Release' EXIT
python -B -u evidence/dense-vector-residual-20261119/harness/ab.py $D/base.dll $D/base-copy.dll $E/raw/control-p1-21.json \
  --rounds 15 --pdf tests/fixtures/pdf-large/real-mixed-120.pdf --first 1 --last 21 --holder agy-C
python -B -u $E/harness/probe_run.py $D/base.dll $D/probe.dll $E/raw/probe-p1-21.json --rounds 11 --holder agy-C
echo BATCH1-DONE
