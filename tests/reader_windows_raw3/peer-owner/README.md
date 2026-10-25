# Actual Windows owner READ of all eleven authenticated Mac captures

Source-only extension, based on `420a876b90e627daa1f1a201cd834fda76472e55`.
Nothing in this directory has been built, syntax-checked or executed locally.
No acceptance is granted until root attaches it to a same-source Windows
Actions run. It changes no existing host, `host_build.py`, `network.py`, owner,
installed package, workflow or old test.

## What executes

The CMake target compiles the **actual**
`apps/reader/desktop/windows_records_owner.cpp` directly and consumes the installed
SDK3.41.0, revisions0.4.0 and raw companion packages0.2.0. There is no copied
owner implementation. CMake records the source SHA, actual owner source SHA256
and emits `windows-peer-owner.map`.

Run it only after the real account-window network receive and both GUI
processes have closed. It opens their **existing** `PROFILE/library.sqlite`
and `PROFILE/library.sqlite.product.sqlite`. Missing mappings or data fail;
there is no SDK import, product attach, receive, repair, write, save or retry.

`prepare.py` accepts the already authenticated `mac_peer.load()` flattened
`OUTPUT/mac/sender` directory. It requires the exact original Mac manifest SHA
`f0960b35374e12827a8966f7022dc3f632e44c87419ca1482288386fb8031566`, source15dab6b2,
run40196978163/attempt1, four formats, fifteen original wires and all eleven
unique records. It rechecks the local original/wire byte identities and complete
declared parent membership. It writes a bounded test-only length-framed expected
file: original strings and base64-decoded selector bytes, preserving NULL versus
present-empty and embedded NUL. This file is not a product/wire codec.
Keep the authenticated Mac proof from `mac_peer.load()` with these reports.

For every manifest record the consumer:

1. Reads actual local mapping using installed public catalog metadata; verifies
   all four retained SDK originals via `exr_library_source()` byte-for-byte
   against the authenticated packet. Reads and compares all fifteen retained
   wires through installed `reader_revision_get_raw_v3`; no manual receive.
2. Uses actual `WINRECORDS_READ`, with the exact source RID/SHA, safe selected
   head, real annotation/progress identity, SDK ID, source byte count and real
   profile pending path. It compares returned anchor version, mode, unit,
   offsets, book/parser/path/page/chapter, selector bytes and NULL tags with the
   manifest capture. It cannot substitute a different head or an offset hint.
3. Calls the configured capture callback **after** successful READ with that
   returned historical record. Production READ itself only validates/decodes
   and does not invoke capture; the report records zero owner READ callback
   calls and one explicit independent callback. READ success is not FOUND.
4. That callback opens a new independent SDK library object and performs actual
   public SDK resolve and create: TXT document anchor; EPUB publication, exact
   spine index/path and bounded pager anchor; PDF/CBZ fixed reader, unique page
   ID and real fixed-page text. It requires SDK `FOUND`, then recaptures the
   resolved range. All numbers, route and selector bytes must match.
5. A separate in-memory NULL-exact callback negative must refuse without FOUND.
   It never becomes a positive record or a manufactured received wire.
6. Compares original source hashes again, every product table's logical rows
   (read-only **product** SQLite connection, including history/outbox), and
   public SDK book/progress/note state before/after. SDK SQL is never queried.
   Bounded EPUB uses its own public EPUB progress/notes APIs; global APIs are
   used only for global books. Fixed notes use the fixed API.

For EPUB there are deliberately two comparisons. The Mac manifest records the
retained wire decoder's `chapter`, which can be NULL. The retained READ result
must preserve it exactly. A real bounded pager anchor is scoped by `part_path`;
fresh comparison uses that same existing Mac/Windows host reconstruction for
chapter, with `epub_chapter_reconstructed_from_part_path=true`. This is explicit
in each row; the consumer does not claim NULL and a string are identical. All
other route fields and selectors must retain their exact presence and bytes.

## Root Actions integration CLI

Run the following **in Windows Actions only**, in the same MSVC-loaded shell
and DLL search environment as the original successful owner probe. These paths
match the existing `host_build.py` output. Adapt only the enclosing build root
if root relocates that output; do not create another profile.

```powershell
$peerRoot = Join-Path $PWD 'build/windows-raw3-host'
$peerSdk = Join-Path $peerRoot 'sdk-stage'
$peerRaw = Join-Path $peerRoot 'raw-stage'
$peerProduct = Join-Path $peerRoot 'product-stage'
$peerNetwork = Join-Path $peerRoot 'mac-network-receive'
$peerPacket = Join-Path $peerNetwork 'mac/sender'
$peerProfile = Join-Path $peerNetwork 'profile'
$peerBuild = Join-Path $peerRoot 'peer-owner-build'
$peerEvidence = Join-Path $peerNetwork 'peer-owner'
$peerFont = Join-Path $PWD 'build/host-font-cache/Reader.otf'

cmake -S tests/reader_windows_raw3/peer-owner -B $peerBuild -G Ninja `
  -DCMAKE_BUILD_TYPE=Release "-DEXR_SDK=$peerSdk" `
  "-DCMAKE_PREFIX_PATH=$peerRaw;$peerProduct;$peerSdk"
if ($LASTEXITCODE) { throw 'peer owner configure failed' }
cmake --build $peerBuild --parallel 4 --verbose
if ($LASTEXITCODE) { throw 'peer owner build failed' }
python tests/reader_windows_raw3/peer-owner/prepare.py `
  --packet $peerPacket --output (Join-Path $peerEvidence 'expected.bin')
if ($LASTEXITCODE) { throw 'exact Mac expectations failed' }
& (Join-Path $peerBuild 'windows-peer-owner.exe') $peerProfile $peerPacket `
  (Join-Path $peerEvidence 'expected.bin') $peerFont `
  (Join-Path $peerEvidence 'first.json')
if ($LASTEXITCODE) { throw 'actual peer owner first process failed' }
& (Join-Path $peerBuild 'windows-peer-owner.exe') $peerProfile $peerPacket `
  (Join-Path $peerEvidence 'expected.bin') $peerFont `
  (Join-Path $peerEvidence 'reopen.json')
if ($LASTEXITCODE) { throw 'actual peer owner fresh process failed' }
```

Equivalent executable positional interface:

```text
windows-peer-owner PROFILE PACKET EXPECTED.bin FONT OUTPUT.json
```

It requires `GITHUB_ACTIONS=true`, reads run/attempt from the actual environment,
and exits 0 only for all eleven successful real READ/FOUND/recaptures and
unchanged state; failures return1 and retain completed rows plus a failure.
The output parent must exist (`prepare.py` creates the evidence directory).
Fresh invocations are distinct real OS processes over the same received data.

## Required collector checks

Keep stdout, `expected.bin`, both JSON files, consumer executable and link map,
owner source SHA, authenticated Mac proof and existing GUI receive evidence.
In root's same-run strict job require both reports accepted, distinct PIDs,
source==GITHUB_SHA, matching run/attempt and executable/owner file hashes;
`actual_owner_reads_and_FOUND==11`; exact manifest ID set and wire SHAs;
all rows' READ/FOUND/equality/NULL-refusal flags; expected framing SHA; four
formats; before/after product and public SDK state equality. Authenticate the
actual executable/provider from map/dependency evidence with the same existing
rules as the original owner consumer. Recompute report/expected/program hashes
in Actions and include them in the original artifact's strict inventory.

Do not promote only one successful process, a partial row list or a generated
report to eleven-record acceptance. Keep the old full owner/bulk/compact/UI and
network assertions. This extension itself grants no GUI record-navigation,
same-source bidirectional, NULL-location FOUND, six-platform or product scope.
