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
