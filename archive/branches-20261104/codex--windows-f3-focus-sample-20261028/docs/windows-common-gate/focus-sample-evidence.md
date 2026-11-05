# Windows F3 focus-border sample correction

The unchanged common-gate run [40638398225/1](https://github.com/NoGod3524/EXReader/actions/runs/40638398225)
at `e330a415b733db18dea5aa6010d13cf3063587fd` failed
`light-theme-page-corner-and-ink`. Its recorded page corner was white
and it found 692 non-white samples. The retained screenshot diagnostic
[40640212303/1](https://github.com/NoGod3524/EXReader/actions/runs/40640212303)
verified artifact 12795210910 and found that the original surround sample
(210,1) landed on the dotted focus rectangle. Adjacent top-edge pixels
alternated black and white; the sample inside the focus rectangle and beside
the page at (212,10) was white.

Commit `95d2a791` changes only the surround sampling position, retaining
the original white tolerance, dark-ink threshold, named check and all remaining
assertions. It also prints the surround and minimum ink sum in the report.

[40640538850/1](https://github.com/NoGod3524/EXReader/actions/runs/40640538850)
tested this fix at `e518efed992c361b48ec46c18c48985238914599`
using the original run's actual candidate and baseline binaries, authenticated
by SHA-256 `4f2a4a5595d7acd7652e6e144f7a6f32f6d10b44cd1931f68897d16e9a616ad7`
and `5c4c77b7f205e0cb7ca3fa6046bdc285b73b0af90980c7c631b30bf6487967e9`.
All 25 native F3 UI checks passed; the new surround sample was white,
the page corner was white, and the minimum ink RGB sum was 0.
Evidence artifact 12795690981 has SHA-256
`9b4ada02b301b1cc7b3d27ad5504fb73cf71bf739bc56fca99dbe0102f05d189`.

The initial diagnostic attempt [40640434248](https://github.com/NoGod3524/EXReader/actions/runs/40640434248)
failed before starting the host because the artifact downloader created an
extra directory. This was corrected without changing the test. The passing
run reuses the previously built executables; it is targeted evidence, not a
newly built same-source complete common-gate run. The original failure, the
two schema-v1 regressions, and the whole gate outcome remain unchanged.
Integrate the test correction deliberately into the authorized common gate,
update its source grant for the exact test change, and run the full gate.
