# Publication positional search

`exr_publication_index_search` searches the same normalized UTF-8 projection as
`exr_publication_search_all`. Results have the same `part`, byte `offset` and byte
`length`, including overlapping matches. Auxiliary parts are skipped; matches do
not cross part boundaries. A result can be passed to `exr_anchor_from_range`, or
used as `exr_target {part, NULL, offset}` with `exr_publication_locate`.

## Worker and batches

Open a separate publication on the host search worker. Access that publication
serially; the UI can keep using its own publication/pager. These C APIs perform
work on the calling thread. They do not start threads or invoke UI code.

```c
exr_index_cursor cursor = {0};
size_t count;
/* Each callback can enqueue a hit immediately. This call returns after 64 hits
   or EOF. Schedule the next call on the worker to continue the same query. */
exr_status status = exr_publication_index_search(
    publication, "寶玉", 0, &cursor, 64,
    enqueue_hit, queue, &control, &count, &error);
/* Continue with unchanged needle/flags until cursor.done; reset cursor for a
   different query. A zero max_results streams the complete result set. */
```

The first query builds only the parts it reaches. To finish in the background,
call `exr_publication_index_build(publication, 0, 1, &control, &stats, &error)`
repeatedly until `stats.complete`. The third argument is the maximum directory
entries per call; zero builds through EOF. Cancellation polls between parts,
blocks and every 4 KiB of tokenization. Interrupted part writes roll back; a later
call resumes from the first unfinished part. A provider's synchronous `load`
callback must return before its cancellation can be observed.

Callbacks must not reenter/free the publication. Failure/cancellation clears
`count` and leaves the supplied cursor unchanged; already emitted callbacks are
provisional until the call succeeds, matching the legacy callback convention.

## Index and memory

Each part stores its normalized text snapshot followed by document-ordered
blocks. Within a block, postings are sorted by `(token, offset)`, giving one
contiguous position list per token. CJK scalars are individual tokens; Latin
words have lowercase word hashes. Additional scalar postings preserve arbitrary
substring searches, punctuation and combining characters. Whole-word queries
use word postings; CJK phrases intersect position lists at the exact byte shifts,
including repeated characters. Other candidates and cross-block phrases are
verified against the snapshot. Word-hash collisions can add candidates but cannot
change the final results.

All postings and snapshots have disk backing. One shared build/query buffer is
at most 64 KiB, plus a small handle. Smaller budgets use smaller blocks; querying
a cache written with a larger budget can use binary reads directly from disk.
This changes I/O cost, not completeness. No text snapshots are retained on the
index heap. The existing linear API keeps its own lazy snapshot behavior.

The default buffer budget is 30% of indexed UTF-8 text, with a 512-byte minimum
for very small inputs. Pass an explicit byte limit to build/load to override it
(minimum 512). `index_info` reports handle plus buffer allocations, their lifetime
peak, text bytes and serialized bytes. Provider document parsing, C runtime FILE
objects/stack, OS file cache, caller-owned query/results and any legacy search
snapshots are separate from these index allocations. The current file format is
limited to 2 GiB and returns an error if exhausted.

## Flags and persistence

Values 0–3 have exactly the legacy flags' behavior: ASCII/Latin-1 simple case
folding, optional case sensitivity, and the existing whole-word boundaries.
There is no stemming, width folding, simplified/traditional conversion or
multi-scalar case expansion. The new API additionally accepts
`EXR_INDEX_IGNORE_DIACRITICS` (4): it strips Latin-1 decomposable accents and
U+0300–U+036F marks while preserving original hit offsets and lengths. The old
APIs still reject bit 4.

```c
/* source_revision: an immutable identity, such as SHA-256 of source bytes plus
   projection options/version. Change it when those inputs change. */
exr_publication_index_save(publication, temporary_path, source_revision,
                           &control, &error);
/* Host can now atomically replace its cache with temporary_path. */

/* On reopening the source, before searching: */
exr_publication_index_load(publication, cache_path, source_revision, 0,
                           &control, &stats, &error);
```

The little-endian format records its version, source revision identity,
publication directory identity, completed-part frontier, text sizes and FNV-1a
payload checksum. Loading checks the checksum, sorted lists and every record
boundary before installing the cache. A stale/corrupt cache returns `EXR_FORMAT`
and leaves an existing index usable. Completed caches do not invoke the document
loader. Partial caches can resume building after reopening. Save stages a complete
copy before opening the destination; host rename supplies crash-safe replacement.
The checksum detects corruption, not malicious tampering or an incorrect
host-supplied revision identity.

The implementation belongs to the layout component and needs no SQLite/FTS
component. PDF `exr_document_search` and all legacy publication search signatures
are unchanged. No desktop UI behavior changes are required to use the new API;
hosts opt into worker-side batching explicitly.

## Repeat acceptance

```powershell
python tools/search_index_bench.py --dll build/search-index/libexreader.dll `
  --book C:/path/to/hongloumeng-24264.epub --cache build/hongloumeng.idx `
  --output evidence/search-index-20261109/benchmark.json
ctest --test-dir build/search-index --output-on-failure
```

The benchmark measures three new-publication cold queries and three reused-index
queries for each of `宝玉`, `寶玉` and `的`. The first batch is 64 callback results;
all remaining results are still delivered. It also measures three rebuild/load
pairs, compares every ordered hit tuple for 20 queries against the linear API,
and checks complete 64-hit cursor continuation. Cold excludes publication open
and does not flush the operating system's file cache. Both APIs must search the
same spelling: the Gutenberg source is traditional Chinese.

