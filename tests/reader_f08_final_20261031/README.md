# Same-source Linux acceptance adapter

This runs the original 44 launches, six causal launches and four body/jump
launches on one newly built executable and seed. It retains all 54 native
frame censuses, including first frames and outliers. Worker operation latency
remains separate from native UI frame cost.

The component builders, original assertions, native probes and frozen budgets
are reused. The final adapter replaces only their historical branch guards
and the extra cohort's older producer download. Its source guard admits the
reviewed integration commit plus this directory and its workflow.

Before the final six-platform validation, update contract.json reviewed_source
to the integrated production commit. No other production, fixture, original
test or build-recipe changes are admitted after that point. The dedicated
adapter-check branch runs only the 20-minute controls. The final-validation
branch runs controls, the original 90-minute full lane, and a 20-minute audit.

The audit authenticates every ZIP entry, checks the shared executable, seed
and observer bytes, replays original assertions and all added actions, rejects
duplicate clock/counter joins, and computes all seven UI categories over all
54 launches. Linux platform_accepted is separate from the six-platform F08 gate.

Validation of the new census used the authenticated original artifacts from
runs 41240011603 and 41241360545: all 7,837 frames and every metric match the
original delivery, including the 295.194 ms maximum and 84 initial frames.
Native and independent duplicate keys, and a foreign source SHA, were rejected.
No new product performance run is claimed by that replay.

The native Android hardware qualification adapter reuses the unchanged ten-case
shelf driver and analyzer. It replaces exactly the cloud identity assignment and
entry guard, declares a native-local run, verifies the actual Arc hardware
renderer and installed Release APK, seals failures, and replays the original
budgets. Sampling has an 1100-second cap with cleanup time within the 20-minute
window. Its APK producer is explicitly the authenticated older 03ec Release;
hardware qualification does not count as final same-source F08 acceptance.
The requested 512 MiB guest heap is clamped by the official emulator to 576 MiB
(growth limit 192 MiB), matching the archived Ubuntu runtime. The 512 MiB
sampled process PSS budget is unchanged.

Native failures also retain terminal display/power/window/input/SurfaceFlinger
state and the actual installed APK identity. Descriptive statistics preserve all
callback rows and first draws without promoting an incomplete UI run. Visible
case screenshots must be nonuniform; black captures are an explicit missing
content failure. Reusing the owned AVD clears only the test helper's retained
output before the original driver runs, matching its fresh-AVD assumption.
