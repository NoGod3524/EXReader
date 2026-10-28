# OpenType contextual lookup miss candidate

The bounded TXT reader spends substantial time applying GSUB to the host's
Noto Sans CJK font. On the diagnostic Windows runner, one chained contextual
lookup has 268 format-3 subtables with no backtrack, and consumed about 25.8 s
of a 3,000-page scan. The candidate caches only a whole-lookup miss proved
independently for every subtable at the current glyph. Each cache hit still
charges and polls every original coverage work unit.

## Windows SDK comparison

[Run 40621870809, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40621870809)
completed successfully. Candidate source is
92a28aa349d511df1bc096d37897839578612a74; the exact baseline is
25c2ef86c5c1c4e72b2c9d9daf8c47873c49bcab. Both installed SDKs were built
on the same Windows runner. The inputs, font, page settings and consumer source
were identical.

- The installed candidate consumer tests passed 7/7, including native shaping,
  complex layout and line-boundary checks.
- A/B comparison of public shaped glyph records and several cancellation
  thresholds passed for the supplied samples.
- All 3,000 page start/end boundaries matched; both ended at byte 1,018,499.
- The measured pagination time was 32,069.551 ms for baseline and 5,576.868 ms
  for the candidate. This is one controlled observation, not a product-wide
  performance acceptance.

The same-run comparison artifact is
[12788186208](https://github.com/NoGod3524/EXReader/actions/runs/40621870809/artifacts/12788186208),
90,460 bytes, SHA-256
2e29576dec4e4af8839e08f9cc11f30950b82797054e7da8e0503c2aefadc4c3.
It expires on 2027-01-26 at 02:35:52 UTC. The artifact identity was obtained
from the run's GitHub metadata; artifact contents are processed in Actions.

The [composed Windows native host run](https://github.com/NoGod3524/EXReader/actions/runs/40622141313)
is separately exercising the original large-TXT scenario. Further independently
constructed contextual-font cases and other platform validations are pending.
The diagnostic implementation and instrumentation are not shipped with this
candidate.

## Three-platform installed consumers

[Run 40622762259, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40622762259)
completed successfully at source 5b7a34ee4f1ce38cf3bcd7cf0220575f4ecf7da9.
The difference from the Windows A/B source above is this evidence document only.
Linux, Windows and macOS each passed the installed TXT anchor consumer (1/1)
and the bounded TXT and native shaping consumers (7/7). This is SDK validation;
the native host and dedicated contextual-font regression remain separate.
