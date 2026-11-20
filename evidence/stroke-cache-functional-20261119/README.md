# B: isolated stroke-coverage cache functional regression

Target inputs: 1beab649c, EXReader-dvpath. Not run at authoring time.

After C then Open release the benchmark lock, have the coordinator authorize a quiet functional run. From EXReader-dvpath:

    pwsh -NoProfile -File evidence/stroke-cache-functional-20261119/run.ps1 -CandidateDllSha256 <SHA_FROM_VERIFIED_1beab649c_BUILD_RECORD>

Optional -BuildDir selects the absolute release build directory (defaults to build/perf). Required DLL hash must originate in a prequalified build record, not an unverified DLL. Runner compiles only the standalone fixture, pins the verified DLL next to the executable, and prints recorded hashes. Preserve stdout/stderr and exit status. Exit 0 and PASS are functional evidence only, not timing/CTest/full corpus evidence.

- Same six-term matrix and geometry repeated eight times before introducing variations. Exact active RGBA per draw against the same DLL with zero-cache control (a never-cancelling callback); background restored for each comparison.
- Live cache tick changes on both insertion and accepted hit, distinguished via array occupancy and byte count. Admission miss and bypass have distinct seen-state behavior. A changed width starts a new entry; restoring the original width hits the original one.
- Narrower nested clip has distinct live identity. Reduced effective stroke alpha, distinct clip, and both together should hit and match uncached pixels; separate non-equality controls confirm they actually affect output. Multiply bypasses standalone stroke but should reuse compound coverage.
- Every explicit matrix term separately gets NaN, both infinities and a finite out-of-range value. Compare cold, warmed and disabled errors, untouched pixels and unchanged cache counters.
- Source review: flags, fill rule when relevant, verbs and transformed points relative to integer origin; strokes add linear stroke matrix coefficients, width, miter, cap, join, dash phase/count/pattern. The approximate hash is followed by field comparison. This is coverage, not final RGBA; clip and paint/alpha are consumed on replay. Blend is consumed on compound replay; standalone is eligible only for Normal and unmasked/non-CMYK. The key checks all six explicit path matrix terms for finite/bounded input before lookup; ineligible input falls through to ordinary validation.
