# GTK navigation: actual painted-page proof

Fixed common source: `07ebe8786434ef384c97ccdb451242d3c6aee6cb`.
The only production difference is the independently reviewed observation commit
`8325f9e1f80ef12193bee0b9eca4d4bac8c4c3be`, whose `examples/linux/reader.c`
blob is `f7608a698b916a0458b7bd9de6edd893a31c6b20`. It records the existing
image draw callback's serial, sensitivity and actual image allocation. It does
not request a draw, flush, synchronize, sleep or change rendering scheduling.
Every other production file, SDK 3.40.0, schema and original navigation backend
and fixtures remain at the fixed common source.

## What the original failed captures contain

Original source `6f7c14e9eea98b60d92c5b4d7796e66576bae4eb`,
[run 40177143143](https://github.com/NoGod3524/EXReader/actions/runs/40177143143),
remains a failed original attempt. Its actual executable SHA-256 is
`5c5a2093abc54fd6ace291002d5928735897908c7afe5786d093b732c397f11d`.
Actions downloaded and authenticated original ZIP `12593244189`, 60,517,704
bytes, SHA-256 `a39ff47a0de4d0b74c76eafbe32451405eecda27ade922525a9929085c43174b`.

The original 1040×820 captures differ at 116,729 pixels. Recomputing the exact
original formula from its retained failure `state.ini` gives bitmap crop
`[172,121,692,761]`, the complete 520×640 page. That crop differs at 52,033
pixels, within local bounds `[0,51,520,551]`. This was not explained by small
color differences in controls outside the page.

OCR of those immutable original pixels identifies `Directory entry`, `Open
entry`, `Show children`, `Cancel directory` and `Full EPUB CFI` inside the
original **after** page crop. Its backing screenshot still contains the
directory interface. The original failure accessibility tree already contains
no dialog and records a sensitive, active main frame. The retained final state
also says `frame_generation=painted_generation=3`. That equality identifies the
accepted SDK frame; it does not identify a new image draw after dialog teardown.
There is no original per-capture before-state record to infer additional timing.

The actual GtkImage allocation was the same as the viewport: origin `[0,63]`,
size 864×757, with the 520×640 pixbuf centered inside it. The new production
observations independently confirm those coordinates. Cropping to a smaller
area or relaxing exact equality is unnecessary.

## New source and exact conditions

The test records the image draw serial immediately before closing the native
directory. Before capturing the page it requires a later actual sensitive
image draw, matching accepted/painted frame generation, restored active native
main window and no visible native directory window. The crop comes from the
actual GtkImage allocation plus the original full bitmap dimensions, with
explicit viewport/window clipping checks. It still compares exact native RGB
bytes and the original frame, notes, progress and product storage identities.

The guard pins `reader.c` to the exact reviewed observation blob and every
other production file to the common base. It compares all 29 original `record`
calls and their conditions, the frame/storage helpers and the existing sleep
calls as syntax trees. No original condition or fixed wait was added, removed
or weakened. The observation and test-wait changes are separate commits.

Tested source `b0db6b8c75601de5bbde7c448b89a934108989bf`,
[run 40183041634](https://github.com/NoGod3524/EXReader/actions/runs/40183041634),
attempt 1, passed the actual full-feature GTK build, original installed F2
130 checks, actual navigation backend, all original 29 native UI conditions
and strict job's 13 rejection controls. Producer `121137941472` and strict
verifier `121138964403` both succeeded.

The close barrier advanced from serial 11 to actual sensitive draw 19; the
capture's later state was serial 22. Both retained frame generations stayed 3.
The complete page before and after has identical RGB SHA-256
`380360e5714fba0ed52cc24ec68d53b10081d189ca6d5924896f6ea2953a9218`.
The strict verifier independently decodes both actual PNGs from the downloaded
same-run ZIP and recomputes those full page crops. The actual new executable is
`b9df306bc67c10e3890b8a9bf47a020cf4d890619bf95c39b524deb6a1f589df`.

| Artifact | ID | ZIP bytes | SHA-256 |
| --- | ---: | ---: | --- |
| Actual host, original/current PNGs, fixtures, logs and reports | 12594907856 | 37251945 | `ad1808006f646a8f52bf9228a67daac6b1951a3b7c468b6d6b6b08db4c31a541` |
| Strict verified summary | 12595415436 | 914 | `7533bf06962597753ef68620b661ded59dabc1bc502d0f4d9f993b7382ada911` |

Both expire `2027-01-23T10:01:19Z`. The validation JSON preserves the earlier
diagnostic identities and original failure. This grant covers this new Linux
GTK navigation source and its exact page proof. It does not reaccept the
original failed source, the full common integration, SDK 3.41, other hosts,
performance or the complete reader product. All execution, syntax checks,
fixtures, PNG/OCR work and artifact processing ran in Actions.
