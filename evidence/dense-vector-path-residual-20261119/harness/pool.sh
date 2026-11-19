#!/usr/bin/env bash
# Step 1: absolute path fill/stroke cost on main 2c27a907a, pages 66-100 at 1200 px.
# Run from the repository root. Takes the global bench lock for the whole batch.
set -e
E=evidence/dense-vector-path-residual-20261119; W=$E/harness; D=$E/_work/dlls
LOCK=/c/Users/Oscar/OneDrive/Desktop/deepseekHarness/ops/bench-lock.ps1
export EXR_IDLE_GATE=off
pwsh -NoProfile -File $LOCK -Holder agy-B -Wait
trap 'pwsh -NoProfile -File $LOCK -Holder agy-B -Release' EXIT
mkdir -p $E/pool
# Same-DLL empty control (two copies of the main DLL), the noise floor for every later code A/B.
python -B -u $W/ab.py $D/main.dll $D/main-copy.dll $E/pool/control-dll-copy.json --rounds 11 --holder agy-B
# Identity control for the omission method: original PDF vs a byte copy, same DLL.
for c in absent path fill stroke polygon-paint polygon-fill polygon-stroke curve-stroke background clip; do
  python -B -u $W/omit.py $D/main.dll $c $E/pool/omit-$c.json --rounds 11 --holder agy-B
done
echo POOL-DONE
