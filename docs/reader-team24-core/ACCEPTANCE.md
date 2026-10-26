# Team24 core combined candidate

Branch: `codex/team24-core`; base:
`d263ce5228838ac90c0a0dc13a5193d4a7739681`.

The input objects were available in the shared Git object database and read
directly: SDK implementation candidate `9d3a3f8bfa06c099ebba0d9e1ba613d276c3af09`
and documentation `4a64ad917fa030b5af7e4f190c1b3394556ac5d4`; S18 WIP
`99ee1a0162998085ce01f1586db4f4df1ece9c0d`; S19 WIP
`446b503072b904c861c4bbee95b87f17fded5dd4`. Only the required paths were restored;
the original worktrees remain untouched.

## Candidate and rounds

One combined workflow, `.github/workflows/reader-team24-core.yml`, binds the
adopted SDK blobs, focused S18 original/raw/default producer and original
9+3+3 binding mutations, and S19 platform provider contracts to one source/run/
attempt. S18's full joint business acceptance remains false for this focused
scope. Windows S19 uses the existing `EXReaderProduct` Win32 target; Linux and
macOS retain their shared feature/SDK model. This is the core candidate, not
completion of the six-platform product.

At most two new complete acceptance runs are authorized for this refactor.
This ledger is additional to all earlier runs; it never resets their history.
New complete round 1: source `91cc13f3c3e31817d7263c7f4be527ac6b185519`,
[40276177912/1](https://github.com/NoGod3524/EXReader/actions/runs/40276177912),
failed preflight because candidate `9d3a3f8b` was local-only and therefore absent
from the runner's fetched graph. No business producer ran. The downstream S18
strict also failed because no named platform producer existed. This round is
retained and counted, leaving one complete round under the original allowance.

Repair: retain the existing combined source tree while merging the exact SDK
candidate as a provenance parent, making its object reachable in the pushed
branch. A bounded `protocol_only` dispatch verifies only the source guard and
source receipt before the remaining complete round. It cannot grant business or
GUI acceptance. No local build, syntax check, test, fixture, benchmark,
screenshot or artifact download/parse has been performed.

Bounded source-only run: source
`6e2d4b09e8fcfb78acbd9afa3f246d6930fa371f`,
[40276347409/1](https://github.com/NoGod3524/EXReader/actions/runs/40276347409),
success. It grants source/receipt binding only.

New complete round 2: the same source,
[40276498769/1](https://github.com/NoGod3524/EXReader/actions/runs/40276498769),
failure. Both authorized complete rounds are now consumed. Specific roots:

- All three S18 producers passed the original three 149-check suites and the
  raw/default 162/21 suites, but graph rejected the correct generated expression
  owner `EXReaderReadingState::reader_reading_state_codec` because our assertion
  incorrectly named its wrapper. The strict job correctly refused the failed
  producers; original 9+3+3 binding mutations have not executed successfully.
- Linux/macOS S19 linked the real shared DSO/host and passed the six mixed-graph
  refusals. Actual jump-history business then returned code 44: its progress
  capture was incorrectly a nonempty range; revision v2 requires a point.
- Windows S19 built the actual `EXReaderProduct.exe`, then its real private-store
  negative hit Ninja's 260-character FetchContent path limit before reaching the
  expected ownership refusal. GUI runtime and its five business paths were
  therefore not reached.

Caller-only repairs now use the exact codec owner, two genuine progress point
captures, preserved pre-cleanup error diagnostics and a short FetchContent base.
No production module or frozen SDK contract is changed by these repairs. They
are **not revalidated**; no third full run is authorized or launched. Root must
decide any additional complete round with these roots visible.

The fixed failed round's original ZIPs and actual program identities are read
only through the Actions `inspect_previous` entry (also `protocol_only=true`).
It cannot build, execute business or grant acceptance. It also checks the
unapplied pure-capture candidate diff structure only; that capability's behavior
remains untested and outside both rounds.

## Additional targeted authorization after independent capability admission

Root subsequently authorized implementing the public pure-capture capability
as an independent three-file candidate and, after its installed focused gate,
one additional S18/S19 targeted Actions round. The candidate was admitted by
`40348964690/1`; see `PURE-CAPTURE-ADMISSION.md` for its exact source, blobs and
original ZIP identity. It is retained on its own branch and is not merged into
the original protected core production tree for this round.

The extra targeted round rechecks the caller/judge repairs in `5ddd1c9b`:
S18 actual three-platform original/raw/default producers and complete original
9+3+3 binding controls, S19 Linux/macOS shared providers and the actual Windows
static Win32 GUI five-business path with the short-path negative. It does not
rerun the four unrelated feature suites, SDK format/corpus or performance
acceptance. The original two complete failures are not renumbered or reset.
This additional run is pending dispatch from the current documentation source.

Update: the authorized targeted round was `40350033756/1`, source
`98b0bb3478588074a9df44bb88d02917397192e7`. S18 all three producers and complete
9+3+3 original semantic binding controls passed. S19 failed on the invalid UUID
test caller at session creation. `STATUS.md` records the accepted S18 original
ZIPs and the separate unvalidated S19 caller repair `8a58c537`; no extra
execution is silently added to the authorization above.

## Historical evidence, kept separate

SDK format combination: `8015c576822d5284dedfea17428ecf1a240befd0`,
[40244430230/1](https://github.com/NoGod3524/EXReader/actions/runs/40244430230),
success; exact candidate SDK tree identity is documented separately.

S18 original joint business replay:
`4af92ba023aa64b3ca6db993f2c7b9cec208e326`,
[40247961052/1](https://github.com/NoGod3524/EXReader/actions/runs/40247961052),
success. Earlier failures `40245930197/1` and `40246888203/1` remain historical.
The old generic fifteen damage controls are not the new original 9+3+3 proof.

S19 failed complete rounds: `40245998177/1`, `40246373859/1`, `40246747578/1`;
cancelled run `40246303666/1` is also retained. The original S19 validation JSON
is unchanged. New static-GUI success must never be inferred from a historical
shared-CLI report.

## Minimum integration boundary

- SDK: only exact `src/rtf.c` and `src/cbz.c` candidate blobs (65 additions,
  9 deletions), with no header/export/preset change.
- S18: restore its existing subtree, then repair actual bindings, original
  semantic mutations, generator-expression origins, and the focused entry.
- S19: restore its existing host-link package/helper/consumer, then use the real
  Win32 static owner and portable shared desktop artifacts.
- Parent: an eight-line macro-gated `s19_features` action in the existing native
  drive entry, the combined workflow and exact source guard. The ordinary UI
  is unaffected by the review-only macro.

The source guard freezes all other paths, including cloud import, WebDAV,
sideload, the seven protected modules, original judges, SDK headers/exports and
budgets. The historical corpus 0/1710 and CPU-budget records are not changed.
Physical devices, screen readers, full six-platform host adoption and delivery
remain outside this run's claimed acceptance.
