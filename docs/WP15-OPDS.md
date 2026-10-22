# WP15 — OPDS 1.x / OPDS 2 stand-alone client (E2)

Module `extras/opds/` (C11, static library `opds`), consumer example `extras/opds/examples/opds_consume.c`,
SDK glue `extras/opds/sdk/` (public `exreader.h` only), fixed service and corpus `tests/opds/`, orchestration
`tools/check_opds.py`, CI `.github/workflows/wp15-opds.yml`. It is **not** part of the default SDK build: the
default C SDK gains no network runtime, no dependency, no ABI/schema change (checked by CI, see *Evidence*).
No LCP, no payment/borrowing service, no account is required or implemented.

Build (SDK optional): `cmake -S extras/opds -B build/opds [-DEXR_SDK=<installed SDK prefix>]`.
Without `EXR_SDK`, `libopds` and the standalone facet regression are built. With it: `opds-consume` and `opds-test`.
All building and testing for this package happens in GitHub Actions (`wp15-opds.yml`, Linux + Windows).

## Model (`include/opds.h`)

`opds_feed` (version 1|2, id/title/updated, `total_results`/`items_per_page`/`start_index`/`current_page`,
`entries[]`, `links[]`, `declared_type_mismatch`) → `opds_entry` (id, title, updated, summary, identifier,
language, publisher, group, `authors[]`, `links[]`, `is_publication`) → `opds_link` (`rel` verbatim, resolved `href`,
`raw_href`, `type` verbatim, title, `indirect_type`, `kind`, `acq`, flags TEMPLATED/PRICED/INDIRECT/PROTECTED).
Unknown relations and media types are preserved; `kind == OPDS_REL_OTHER` tells the host it was not recognised.
Navigation (`OPDS_REL_SUBSECTION`, `START`, `UP` …) and acquisition (`OPDS_REL_ACQUISITION` + `acq`) are separate;
pagination is `opds_fetch_next` (rel=next); search is `opds_search_url` + `opds_fetch_feed`.

Module 0.2 adds `opds_feed_facets(feed, &count)`: groups expose a title and choices with resolved
`opds_link`, active state, and an exact nonnegative 64-bit item count (`-1` means absent).
Pointers are borrowed until `opds_feed_free()`. Existing public feed, entry and link sizes stay fixed.
The host displays the choices and passes the selected `link.href` to `opds_fetch_feed()`;
the normal per-origin credentials, redirect and transport rules apply.

## Support table

| Area | OPDS 1.x Atom | OPDS 2 JSON | Explicit refusal (tested) |
| --- | --- | --- | --- |
| Document | `atom:feed` in the Atom namespace, any prefix, UTF-8 (BOM ok) | object with `metadata.title` and one of `links`/`navigation`/`publications`/`groups`/`facets` | other roots/namespaces, HTML, JSON arrays, other encodings (`unsupported`), DTD/DOCTYPE, undefined entities, duplicate attributes, undeclared prefixes → `format` |
| Navigation | `entry/link rel=subsection` or any other rel (kept verbatim, `kind=OTHER`) | `navigation[]`, `groups[].navigation[]`, link `rel` string or array (joined by a space; default `subsection`) | link without `href`, entry/feed without title → `format` |
| Publications | `entry` with `author/name`, `dc:identifier|language|publisher` (dc or dcterms), summary/content | `publications[]`, `groups[].publications[]`: title (string or localized object → first value), author string/object/array, identifier, language (string/array), publisher, description, modified, `images[]` | publication without metadata/title → `format` |
| Facets | feed links with `rel=http://opds-spec.org/facet`, grouped by `opds:facetGroup` (empty if absent), `opds:activeFacet`, `thr:count` | `facets[].metadata.title` and `links[]`, active `rel=self`, `properties.numberOfItems` | malformed groups/counts, multiple active OPDS1 choices per group → `format`; groups and total choices each capped by `max_entries`, choices per group by `max_links_per_entry` → `limit` |
| Links / base | `xml:base` on feed, entry and link; relative, scheme-relative, dot segments, query-only; bytes outside RFC 3986 are percent-encoded once (existing `%XX` kept) | links resolved against the document URL after redirects | URL > 4096 bytes → `format` |
| Pagination | rel `next`/`previous`/`first`/`last` + OpenSearch `totalResults/itemsPerPage/startIndex` | same rels, `numberOfItems/itemsPerPage/currentPage` | page budget and revisit (loop) → `limit` |
| Search | `rel=search` to an OpenSearch description (first `atom+xml`/`opds+json` Url) or a templated href | `rel=search` with `templated:true` | no search link, non-templated href, template operators `+ # / . ;`, unknown *required* variable → `unsupported`; `https` → `needs_host` |
| Template variables | `{searchTerms}` `{startPage}` `{count?}` … (optional `?` ⇒ empty) | `{query}` `{q}` `{?query,page}` `{&query}` | percent-encoded UTF-8, only unreserved bytes unescaped |
| Acquisition | `rel` `http://opds-spec.org/acquisition[/open-access|/sample|/preview|/borrow|/buy|/subscribe|<future>]`, `opds:price`, `opds:indirectAcquisition` | same rels in `links`/`properties.price`/`properties.indirectAcquisition` | borrow, buy, subscribe, priced, Adept/LCP/AxisNow license types → `needs_host` before any request; samples are never chosen unless asked by type |
| Media types | any, compared case-insensitively without parameters; content is sniffed for EPUB/PDF/ZIP/HTML | same | declared type vs content mismatch → `mismatch` (see below) |
| Errors | HTTP 401 → `auth_required` (+scheme), other non-2xx → `http` (+status) | same | timeouts → `timeout`, cancel → `cancelled`, truncated bodies → `io` |

Not supported (reported, never silently ignored): `indirectAcquisition` resolution,
borrow/payment flows, DRM, templated acquisition links, HTTPS inside the reference transport (host transport needed),
non-UTF-8 XML, HTTP compression, HEAD/POST.

## Network, credentials, budgets

* The host owns the transport. `opds_transport.fetch` performs exactly one request and never follows redirects;
  `opds_socket_transport()` is the reference plain-HTTP/1.1 implementation (POSIX sockets / Winsock, chunked and
  identity bodies). `https://` returns `needs_host`; a host plugs in its TLS stack through `opds_config.transport`.
* Timeouts are inactivity timeouts (`limits.timeout_ms` per connect/send/receive wait, default 10 s). Cancellation
  is polled every ≤50 ms while waiting and per received chunk (`opds_control.cancelled`). Name resolution is not
  cancellable.
* Redirects (301/302/303/307/308) are followed by the client, `max_redirects` (5), loops are detected, non-HTTP schemes
  and https→http downgrades are refused. The `Authorization` value supplied in `opds_config` is bound to one origin
  (`scheme://host:port`); it is attached only to requests for exactly that origin, including after redirects, and is
  dropped on any cross-origin hop (`opds_client_stats(...).credentials_dropped`). It is copied, never logged and zeroed on free.
* Logging is by callback and carries `GET <url> -> <status>` with userinfo removed and values of secret-looking query
  keys replaced by `REDACTED`.
* Budgets (`opds_limits`, independent of the SDK's): feed bytes 4 MiB, elements 200000, entries 2000, links per entry
  128, nesting 48, redirects 5, pages per crawl 50, download bytes 256 MiB, timeout 10 s. Exceeding any returns
  `OPDS_LIMIT` with a message; `Content-Length` over budget is refused before reading the body.
* `opds_client_begin_crawl` resets the page counter and visited set; refetching a URL inside a crawl is `limit`.

## Download and consumption

`opds_download` / `opds_download_url(client, link|url, dest_path, options, control, result, error)`:

1. Acquisition links that need a host capability return `needs_host` without any request.
2. `dest_path` must be a plain file name (no `.`/`..`, reserved characters, trailing dot/space, device names) in an
   existing directory; a directory, symlink/reparse point or special file as destination is refused (`argument`).
3. Bytes stream into an exclusive-create temporary file **in the destination directory**
   (`.opds-<pid>-<n>-<name>`, extension preserved), hashed (SHA-256) and flushed.
4. Content is sniffed (`%PDF-`, ZIP, ZIP with a leading `mimetype` = `application/epub+zip`, HTML). The declared
   type (link type or `options.media_type`) must agree with the sniffed signature; HTML for anything but HTML,
   EPUB declared but plain ZIP, PDF declared as EPUB etc. → `mismatch`, nothing is published. When the content has no
   signature, a non-generic `Content-Type` that disagrees is also `mismatch`. A disagreeing header with matching
   content is accepted and flagged (`header_type_mismatch`).
5. The optional verifier runs on the temporary file. `opds_sdk_verify` opens EPUBs with `exr_publication_open`,
   loads the first part and reads its text; failure → `unreadable`, nothing is published. A verifier answering
   `unsupported` (PDF and everything else here) publishes the file with `readable = OPDS_READ_UNKNOWN`. Without a
   verifier `readable` is also `UNKNOWN`: **a successful download never means the book is readable.**
6. Publication is atomic: `link()`+`unlink()` (POSIX, never replaces) or `rename()` when replacing; `MoveFileExW`
   (Windows). An existing destination with identical SHA-256 is a no-op (`already_present`, success, same bytes); with
   different content the policy decides: `OPDS_EXISTING_FAIL` (`exists`, destination untouched) or `REPLACE`.
7. Cancellation, timeouts, I/O errors, budget refusals, mismatches and verifier failures remove the temporary file
   and never touch the destination.

## Consumer example

`opds-consume --start URL --out DIR [--follow TITLE]... [--search TERMS] [--pick TITLE] [--type MIME] [--max-pages N]
[--replace] [--auth-env VAR [--auth-origin URL]]` runs catalog → section(s) → search → paging → selection → download →
SDK open, prints one JSON line and exits 0 only when the book was published **and** the SDK read it. Credentials are read
from the named environment variable and never printed.

Host integration (follow-up package, not done here): link `libopds` (+ `opds_sdk` for verification), supply a transport
if TLS is required, keep credentials in the platform store and pass them per origin, choose the destination directory
and call `opds_download`, then hand the published file to the normal library import path.

## Evidence (CI)

`tools/check_opds.py` starts `tests/opds/server.py` (two loopback origins A and B, fixed corpus in
`tests/opds/corpus/`, dynamic pagination/search/redirect/stall/chunk/truncation/auth routes), runs `opds-test`
(~60 named cases; OPDS1 and OPDS2 each ≥10 covering navigation, pagination, search, acquisition, auth, bad data and
budgets, plus network and download cases) and eight `opds-consume` runs, audits the server request log (origin B must
never see credentials), scans every output for the fixture credentials, verifies no `.opds-*` temp file remains, and
proves the default SDK is untouched (git tree hashes of `src`, `include`, `cmake`, `CMakeLists.txt`, `bindings`,
`tests/fixtures` and the existing workflows equal the baseline `a2552d7`; changed paths are owned paths only; runtime
`exr_version()`/`exr_abi_version()` equal the headers). Output: `wp15-opds-<os>.json` (per-case id, protocol, category,
request class, input SHA-256, expected/actual, request lines, library/binary SHA-256 identity) uploaded as the
`wp15-opds-<os>` artifact. A case that is missing, skipped or failing fails the job.

Facet coverage additionally runs `opds-facets` in both platform jobs before the existing acceptance driver.
`facet-result.json`, CTest log and the facet binary hash are preserved in the same artifact and summary.
It covers grouping, active selection, base resolution, localized group titles, absent/zero/INT64_MAX counts,
malformed inputs, budgets and pointer lifetime. The existing `o2_groups_facets` service case now selects a
facet URL through the client and checks the returned publication/acquisition links. Linux also runs the
standalone parser under ASan/UBSan with leak detection.
The mapping follows [OPDS 1.2 facets](https://specs.opds.io/opds-1.2.html)
and [OPDS 2.0 facets](https://specs.opds.io/opds-2.0.html).

## Known gaps

HTTPS and TLS (host transport), indirect-acquisition resolution, borrow/buy/subscribe/LCP (explicit
`needs_host`), name-resolution cancellation, symlink-destination test on Windows (POSIX only), PDF/CBZ SDK verification
(requires the `exr_pdf` component, outside this core-only consumer), integration into the Windows/Apple/Android hosts.
