# Reader OPDS browser (J02)

Optional reader package `apps/reader/opds-browser/`. It turns the frozen standalone
OPDS module (`extras/opds`, `OPDS_MODULE_VERSION 0.2.0`) into a paged catalogue and
search browser with a two-phase download: a network phase that never calls the SDK, and
an SDK-owner phase that imports the staged file only through the public sideload route.
It adds no feed parser, no payment, no borrowing and no DRM handling.

Fixed start `f43baf9182d75907c0cb5d6f77048f27bca8c950`, branch `codex/reader-opds-browser`.
Everything is built, installed, trusted, served and measured in GitHub Actions
(`.github/workflows/reader-opds-browser.yml`); the local machine only edits source.

## Package layout

| Path | Role |
| --- | --- |
| `include/reader_opds_browser.h` | public C ABI of the network phase |
| `include/reader_opds_import.h` | public C ABI of the SDK-owner phase |
| `src/browser.c` | snapshots, feed sequences, cursors, search, acquisition policy |
| `src/transport.c` | scheme dispatch: module socket transport for http, platform TLS for https |
| `src/tls_winhttp.c` / `src/tls_curl.c` | https transports (WinHTTP, libcurl) |
| `src/import.c` | staged-file re-verification and the public sideload import |
| `CMakeLists.txt` | static libraries `reader_opds_browser` / `reader_opds_import`, install + CMake package |
| `examples/reader_opds_consume.c` | minimal in-tree consumer (`-DREADER_OPDS_BUILD_EXAMPLE=ON`) |

The frozen `extras/opds` tree has no install or export rule and is protected, so this
package compiles those unchanged sources into `libreader_opds_browser.a` and installs
`opds.h` next to its own headers. An installed consumer therefore links exactly one
library plus the SDK and sideload packages it was built against.

## Contract

`reader_opds_config` (struct_size, limits, transport, credential_origin, authorization,
staging_dir). All limits are the module's own and may only be lowered; 0 selects the
module default. `staging_dir` is validated at create time (must exist). Credentials are
copied, bound to one origin and only attached to requests for that origin; the module
drops them on a cross-origin redirect and `reader_opds_browser_stats` reports the count.

`reader_opds_page` is an immutable, self-contained snapshot of one page: every display
field of the module's feed/entry/link/facet model is copied into one arena bounded by
`READER_OPDS_SNAPSHOT_BYTES` (16 MiB), including `raw_href`, `indirect_type`, facet
`rel`/`flags`/`number_of_items`. `reader_opds_page_free` does not need the browser.

Pagination is bound to a feed identity: `SHA-256("reader-opds-seq-1" || kind || url)`
for the sequence start (or the resolved search URL), so a search's identity covers its
terms. A cursor is `c1-` + 32 hex digits derived from a per-browser nonce, the sequence
identity and the next URL; `reader_opds_resume` refuses an identity/cursor pair that
does not match the live sequence (`READER_OPDS_CURSOR`). Eight sequences are kept and the
least recently used one is evicted with its cursor; a page already shown, a next link to
another origin and a sequence over `limits.max_pages` are not offered (no cursor).

Acquisition policy: PROTECTED, BUY, BORROW, SUBSCRIBE, SAMPLE, PRICED, INDIRECT are
refused before any request (`NEEDS_HOST`, a sample `UNSUPPORTED`); only a FREE link of
EPUB/PDF/CBZ is fetched. The file name is `opds-` + 24 hex digits of the link identity +
an extension from the declared media type. Declared-vs-sniffed type (`MISMATCH`), a
container envelope check (`UNREADABLE`) and the byte budget run before the single atomic
publication; a second identical download reports `already_present`.

Threading: a browser is single-owner. Any call that overlaps another call - including one
made from inside the control callback - returns `READER_OPDS_BUSY` without side effects;
no page is recorded as visited unless the call returned it, so a cancelled or failed call
can be repeated with the same cursor. The browser never touches the SDK.

`reader_opds_import_staged` runs on the SDK-owner thread, re-reads the staged file in
64 KiB steps and requires the recorded byte count and SHA-256 (`EXR_IO` otherwise), then
imports only through `exr_sideload_import_file`. The SDK alone decides readability: a
container that passed the envelope check but is not a book returns the SDK's status and
leaves the library unchanged. Neither the file nor the library is released or deleted.

## TLS

`reader_opds_default_transport()` dispatches http to the module's socket transport and
https to the platform implementation: WinHTTP on Windows, libcurl elsewhere, both with
the system trust store, host-name verification, no redirect following, no proxy, no
cookies and identity encoding only. `READER_OPDS_TLS=OFF` builds a network-only library
in which https returns `NEEDS_HOST`; `reader_opds_tls_available()` reports which build
is installed.

## Acceptance (Actions only)

`check_opds_browser.py` creates an ephemeral CA, trusts it in the runner store, serves
two plain origins and one TLS origin and runs the two installed consumers. Named cases
cover OPDS 1 and OPDS 2 snapshots (non-ASCII title/author/summary, identifiers, facets,
navigation), pagination with loop refusal and stale/foreign cursors, OpenSearch and
templated search with UTF-8 terms, refusal of buy/borrow/protected/priced/indirect/sample,
a fake extension (`MISMATCH`), a broken container (published, then rejected by the SDK),
duplicate acquisition, cancellation, reentrancy (`BUSY`), lowered budgets, staging
requirements, credential isolation (server-side proof that the plain origin never saw an
Authorization header), TLS browse and TLS acquisition, and the import phase (size/digest
mismatch, wrong media type, missing descriptor, broken book, cancellation before commit,
library still usable). `check_artifacts.py` then authenticates the three platform ZIPs,
recomputes their digests and requires identical named outcomes.

Reproduce from a clean checkout:

```
cmake --preset reading-library && cmake --build --preset reading-library && cmake --install build/reading-library
cmake -S extras/sideload -B build/sideload -G Ninja -DEXR_SDK="$PWD/build/reading-library/stage" -DCMAKE_INSTALL_PREFIX="$PWD/build/sideload-stage"
cmake --build build/sideload && cmake --install build/sideload
cmake -S apps/reader/opds-browser -B build/opds-browser -G Ninja -DEXR_SDK="$PWD/build/reading-library/stage" \
  -DCMAKE_PREFIX_PATH="$PWD/build/sideload-stage" -DREADER_OPDS_BUILD_EXAMPLE=ON -DCMAKE_INSTALL_PREFIX="$PWD/build/opds-browser-stage"
cmake --build build/opds-browser && cmake --install build/opds-browser
cmake -S tests/reader_opds_browser/consumer -B build/opds-consumer -G Ninja \
  -DCMAKE_PREFIX_PATH="$PWD/build/opds-browser-stage;$PWD/build/sideload-stage;$PWD/build/reading-library/stage"
cmake --build build/opds-consumer
python tests/reader_opds_browser/check_opds_browser.py --consumer build/opds-consumer/opds-consumer \
  --import-consumer build/opds-consumer/opds-import-consumer --fixtures tests/fixtures --evidence build/opds-evidence
```

The trust-store step needs `sudo` (Linux/macOS) or `certutil` (Windows); it is why this
driver is Actions-only.

## Limits and known gaps

* No payment, borrowing, DRM, indirect-acquisition resolution or templated acquisition:
  such links are refused with `NEEDS_HOST`/`UNSUPPORTED` before any request.
* Formats are EPUB, PDF and CBZ (the sideload ceiling of 128 MiB applies); anything else
  is refused as `UNSUPPORTED` at acquisition time.
* The frozen module fixes the request `User-Agent`; the browser exposes no such knob and
  a host cannot override it without changing the module.
* The module's socket transport is plain HTTP/1.1 with identity encoding; https relies on
  the platform transport and its system trust store (a private CA must be installed by the
  host, as the Actions run does).
* The product hosts are not wired: this package ships an installable library, an example
  and installed-consumer probes; root owns host integration.

## Recorded evidence

Tested source `dcf77c2776d7cdce180f303d2a85152cf538a8d6` (branch `codex/reader-opds-browser`),
run [40126660557 attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40126660557):
all four jobs passed, every platform reported the same 60 named cases, and the strict job
re-hashed the two consumer executables out of each ZIP before comparing outcomes.

| Job | ID | Result |
| --- | --- | --- |
| opds consumers (ubuntu-22.04) | 120969458912 | success |
| opds consumers (windows-2022) | 120969458897 | success |
| opds consumers (macos-15) | 120969458713 | success |
| strict opds evidence | 120970046951 | success |

| Artifact | ID | Bytes | sha256 | Expires |
| --- | --- | --- | --- | --- |
| reader-opds-browser-linux-40126660557-1 | 12573492675 | 4275700 | `ae999f0990a4cdd0a1627df46736c5a580bb94e59988061ff2b63f3696db7d65` | 2027-01-22 |
| reader-opds-browser-windows-40126660557-1 | 12573277935 | 3386286 | `3fb40aa1d4f95117f1af87a2c78828791001d817e77cd2ea37fd2f66cb13210d` | 2027-01-22 |
| reader-opds-browser-macos-40126660557-1 | 12573547771 | 3665408 | `50c97a59d8194bea9995399c880d9ff9220bccf8b74a65aeea08643bb69f41d4` | 2027-01-22 |
| reader-opds-browser-evidence-40126660557-1 | 12573537844 | 1623 | `2cf6c368cf8ed9634cf71b17fd2e5d9192621a87c8a267c45c4330fdd3398ad3` | 2027-01-22 |

Executed consumers (bytes / sha256), re-hashed from the artifacts by the strict job:

| Platform | Consumer | Bytes | sha256 |
| --- | --- | --- | --- |
| linux | opds-consumer | 147920 | `632c959389471ffb1eaf4df341ca215b228ca0e21bebe9ac127caca02403d281` |
| linux | opds-import-consumer | 8582504 | `c61ab8b59bbcba654404d8b36af7634ec6b3a06c5a34740287acd2f462bc44e7` |
| windows | opds-consumer.exe | 292352 | `411b903244bb6a3e7f7c53bb10ccfa5ff8f807b3cf777f66728a5dbcb8c7c499` |
| windows | opds-import-consumer.exe | 6133760 | `cbee3c7d60748223096954a60ab0d6ff0198162fccc05c1c83b58828409f0d95` |
| macos | opds-consumer | 158816 | `caefeaac03394d8615b0c38d3483497864f7a4f060d1431b5a1d6c5465303974` |
| macos | opds-import-consumer | 7000312 | `2032fa5abb763ff5288c9aa105b4f820843be72decd9e5e4196b6bc98c0dcdef` |

Every platform reported `accepted: true`, 60/60 named cases, 36 recorded fixture requests,
two TLS requests, and `plain_requests_with_authorization: 0` while the credential origin
received exactly one Authorization header.

A previous run (40125592894, source `7c2b274e`) passed the same four jobs before the consumer
binaries were bound into the evidence; it is kept as history, not as the accepted source.

Retained failures, each with its own artifacts:

* `4e873f22` run 40123942977 — the installed consumer did not compile: greedy hex escapes.
* `46911446` run 40124481258 — wrong import expectations, a no-replace collision, a one-byte
  WinHTTP header buffer and a macOS `getfqdn` stall in the fixture service.
* `eef73089` run 40124883828 — superseded before it could pass.
* `f82c0134` run 40125267330 — cancelled on purpose once superseded.
* `935e47a9` run 40126530848 — cancelled on purpose after the evidence job matched the
  uploaded `CMakeCache.txt` as a third consumer entry; fixed before it finished.

This section and `docs/validation/reader-opds-browser.json` are committed with `[skip ci]`
after the run. No source, test, workflow or fixture byte changed, so the tested source stays
`dcf77c27` and the branch head differs only in documentation.

Not granted: product-host wiring, PDF/CBZ import through the SDK (only envelope, staging and
EPUB import are exercised), performance/CPU/accessibility/real-device claims, and release
packaging or signing.

## T07 independent review (2026-10-25, pending new Actions acceptance)

Fixed review start: `3ca9d9fed564dbcba11fc95a034244c5cfe8c762`.
The original tested source `dcf77c2776d7cdce180f303d2a85152cf538a8d6`
run `40126660557` was independently checked through the GitHub jobs API:
all three installed-consumer jobs and strict evidence job completed successfully.
The review start differs from that tested source only in the two evidence documents.
This historical success does not validate the following new changes.

Source tracing covered snapshot allocation/copy/free, cursor sequence ownership,
relative href resolution delegated to the frozen OPDS module, acquisition class and
media policy, credential origin isolation, reentry guard, network staging and public
SDK-owner import. The adapter does not add a parser or network backend.

Confirmed cleanup defect: a denied removal followed by a denied reopen was
reported as successful discard. The receipt is now retained and IO returned unless
removal reports ENOENT. The installed C consumer locks the file on Windows or denies
staging-directory access on POSIX, verifies IO and unchanged receipt, then restores
access and preserves the original successful/idempotent discard regression.

Strict review adds completed job/run/attempt authentication, artifact run identity,
unique and unambiguous ZIP members/reports, exact platform binary identities, and
strict boolean successful unique case outcomes with count consistency. Executable
negative cases run in Actions before the strict real-artifact authentication.
Original cases and historical failures remain intact. No new platform, host UI,
performance or real-device scope is claimed. No local builds or tests were run.

Further transport tracing found that POSIX libcurl inherited ambient proxy variables
although the public API promises no proxy. It now explicitly disables proxies;
the real HTTP/TLS consumer subprocesses run with poisoned proxy variables and no
NO_PROXY exception. Windows already uses explicit no-proxy transport. These
changes require fresh three-platform CI. A hard wall-clock deadline for slow
streaming responses remains unverified across native transports; the existing
connection/read/low-speed limits are not promoted to such a claim.
