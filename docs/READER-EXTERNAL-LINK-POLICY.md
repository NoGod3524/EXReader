# EXReader external link policy

Optional native package **EXReaderLinkPolicy 0.1.0**, ABI 1. It classifies the raw
`href` / `src` string of a link inside book content and returns an explicit
action plus the original display text. The package never opens, fetches, resolves
DNS, reads files, launches processes or renders anything, and holds no global
mutable state. It is not wired into any host yet; the hosts stay with their
owners and this package reaches them only through the public C ABI.

- Source: `apps/reader/link-policy`
- Consumers and fixtures: `tests/reader_external_link_policy`
- Workflow: `.github/workflows/reader-external-link-policy.yml`
- Fixed start: `f43baf9182d75907c0cb5d6f77048f27bca8c950`
- Frozen SDK: `9854061be331fe603a1822d9b2b36ee357154927` (3.40.0, ABI 1)

## Contract

```c
reader_link_status reader_link_policy_create(const reader_link_policy_options *, reader_link_policy **, reader_link_error *);
void                reader_link_policy_destroy(reader_link_policy *);
reader_link_status reader_link_classify(const reader_link_policy *, const char *text, size_t size,
                                        const char *base_path, const reader_link_control *,
                                        reader_link_result *, reader_link_error *);
void                reader_link_result_free(reader_link_result *);
const char         *reader_link_action_name(reader_link_action);
const char         *reader_link_reason_name(reader_link_reason);
```

Actions:

| action | meaning | who may act |
| --- | --- | --- |
| `REJECT` | deny by default: forbidden scheme, malformed escape, control, bad authority, path escape, unknown scheme | nobody; draw `display` as text |
| `INTERNAL` | stays inside the book: fragment, CFI or relative container path | hand `display` offsets to the public SDK resolver |
| `NEEDS_HOST` | allow-listed external target | host, after its own confirmation prompt |

The policy never maps a container path to a chapter and never parses a CFI. For
`INTERNAL` results it validates syntax and reports `path_len`,
`fragment_offset` and `fragment_len` as offsets into the returned
`display` copy; the host passes that substring to `exr_document_resolve`
or the CFI API. Chapter guessing, spine indexing and resolution stay with the SDK.

### Ownership and lifetime

- The policy is created by the caller, immutable afterwards, freed by the caller;
  `reader_link_policy_destroy(NULL)` is a no-op.
- Input bytes and `base_path` are borrowed for one call.
- `reader_link_result.display` is a library-allocated copy that stays valid until
  `reader_link_result_free` and does not depend on the input buffer or on the
  policy surviving. It is NUL terminated and `display_len` counts bytes without
  that terminator. Over-limit input yields `display == NULL`, `display_len == 0`.
- Free every result whose status was `READER_LINK_OK` exactly once; free is
  idempotent on zeroed and already-freed values.

### Threads and reentry

- `reader_link_classify` is const and may run concurrently on one policy from any
  threads; the policy is not thread-affine. `reader_link_policy_destroy` needs
  exclusive access.
- The cancel callback runs synchronously on the calling thread and may call
  `reader_link_classify` again, including on the same policy, but may not destroy it.

### Errors, cancellation, commit boundary

- `READER_LINK_ARGUMENT`: NULL/invalid arguments, unset `struct_size`, invalid
  options, invalid base path.
- `READER_LINK_MEMORY`: allocation failed, nothing committed.
- `READER_LINK_CANCELLED`: the control asked to stop, nothing committed.
- On any non-OK status `*result` is zeroed, except when `result->struct_size` is not
  `sizeof(reader_link_result)`, where the struct is left untouched (it is not ours to
  write). A rejected link is **not** an error: status `READER_LINK_OK`, action
  `REJECT`, reason naming the first problem found.
- Cancellation is polled on entry, at least every 4096 input bytes, and once
  again after classification but before anything is committed, so a late cancel
  frees the copy and never publishes it.

### Limits

| limit | value |
| --- | --- |
| default input | 8192 bytes (`READER_LINK_DEFAULT_INPUT_BYTES`) |
| option ceiling | 65536 bytes (`READER_LINK_MAX_INPUT_BYTES`); larger options are `ARGUMENT` |
| internal path / fragment | each < 2048 bytes, <= 256 segments |
| extra allowed schemes | 8, <= 16 characters each |
| display copy | input length + 1, only when input <= the active limit |

Limits are enforced before any allocation proportional to the input, and a
rejected link allocates nothing beyond the display copy.

## Allow list and deny list

Built-in allow list: `http`, `https`, `mailto`. Callers may add up to eight schemes
(case-insensitive, normalised to lower case in `result.scheme`).

Hard deny list (creation fails if a caller tries to add one): `javascript`,
`vbscript`, `jscript`, `livescript`, `mocha`, `data`, `file`,
`blob`, `filesystem`, `about`, `jar`, `view-source`, `shell`,
`search`, `search-ms`, `wyciwyg`, `intent`, `content`, `chrome`,
`res`, `resource`, `cmd`, `powershell`, `wscript`, `cscript`,
`mshta`, `ssh`, `telnet`, `smb`, `ldap`, every `ms-*` scheme, and
single-letter schemes (drive letters such as `C:`). A syntactically valid scheme that is
neither allow-listed nor denied is `REJECT` / `UNKNOWN_SCHEME`.

Rejections also cover: empty input, over-limit input, invalid UTF-8, C0/C1/DEL,
bidi controls, line/paragraph separators, BOM and Unicode spaces, leading/trailing
space or any space inside an external target, backslash, malformed `%XX`, `%00`,
encoded controls in container paths, encoded `/` or `\`, `%2e` dot segments,
double escapes (`%25XX`), absolute paths, protocol-relative `//`, path escape above
the container root, userinfo (`@`) or encoded authority, empty/duplicate labels, ports
outside 0-65535, `?` or `:` inside an internal path, and two `#` characters.

Percent escapes are validated per URI component. In an external target only the
query may carry encoded C0/DEL bytes (a `mailto` body such as `x%0D%0Ay` is the
documented positive case), and that region ends at the first `#`: the authority,
the path and the fragment itself reject encoded controls, so
`https://example.com/?q=x#%0A` is rejected. A `?` inside the fragment is literal
text and never starts query data, so `https://example.com/#a?b%0A` is rejected
while `https://example.com/#a?b` is kept. A `#` fragment keeps literal `/` and
`:` because ids are opaque text, but its escapes must decode to valid UTF-8:
`#a%FF`, `#%E2%82` and `https://example.com/#%FF` are `BAD_ESCAPE`, and
`#%E7%AB%A0%E8%8A%82` is an accepted INTERNAL fragment.

`result.flags` reports `DISPLAY_UNSAFE` (display bytes contain invalid UTF-8 or
controls and must be escaped before drawing), `NON_ASCII_HOST` (show punycode or warn)
and `HAS_FRAGMENT`.

## Host integration (not performed here)

1. Create one policy per reading session (stack or heap, caller-owned).
2. For each link attribute of the book content, call `reader_link_classify` with the
   document's container path (for example `exr_navigation.base`) as `base_path`.
3. `INTERNAL`: pass `display` (or its path/fragment parts) to
   `exr_document_resolve` / the CFI resolver.
4. `NEEDS_HOST`: show `display` and the scheme, ask the user, then let the
   host open it with its own external-open API. The policy never opens anything.
5. `REJECT`: draw `display` as inert text (escape it when `DISPLAY_UNSAFE`).
6. Free every result exactly once; destroy the policy when the session ends.

## Reproduce in Actions

The workflow builds the frozen SDK and the package from source, installs it,
then compiles five independent consumers against the **installed** prefix only:

| consumer | what it proves |
| --- | --- |
| `link-probe` | fixture table, limits, argument errors, output lifetime, policy interleaving |
| `link-cpp-consumer` | C++17 header use, concurrent classify, reentrant cancel, display outliving policy |
| `link-worker` | allocation-failure paths and cancel points (source build with test hooks only) |
| `link-sdk-consumer` | authored navigation from the frozen SDK classified, INTERNAL resolved by the SDK, external refused by the SDK |
| `link-unsafe-control` | negative control for the symbol audit; never executed |

`check_link_policy.py` fixes every expectation before reading consumer output,
runs each consumer, and writes `report.json` with 37 named outcomes. `check_artifacts.py`
then authenticates the three same-run ZIPs through the GitHub API, re-computes
their digests, and compares the report against the installed library, header and
consumer bytes inside the same ZIP.

## Root review fixes

Two source reviews (`docs/handoffs/reader-next-wave/J06-ROOT-REVIEW.md`) found
three contract gaps, all in `src/policy.c`. Each fix changed behaviour, so each
round was re-tested from its own source and no green was transferred.

**Round 1** (landed in `b3a01821`):

1. `external()` applied the query escape rules to the whole target, so `%0A`,
   `%0D`, `%7F` in an authority, path or fragment still became `NEEDS_HOST`.
   Escapes are now checked per component and only query data may carry encoded
   C0/DEL bytes, which keeps the documented `mailto:…?body=x%0D%0Ay` positive.
2. `internal()` checked fragment hex and controls but never decoded the escapes,
   so `#a%FF` became `INTERNAL`. Fragments now run through the same UTF-8 state
   machine as container paths: `#a%FF`, `#%E2%82`, `#%C0%AF` → `BAD_ESCAPE`.

**Round 2** (landed in `6fd6031c`): the round-1 query check still ran to the end
of the target, so a fragment that followed a query kept the query allowance and
`https://example.com/?q=x#%0A` was accepted. The query region now ends at the
first `#`; the fragment after it is validated as a fragment (encoded controls
and non-UTF-8 escapes rejected), and a `?` inside a fragment never starts query
data, so `https://example.com/#a?b%0A` is rejected while `https://example.com/#a?b`
is kept. `https://example.com/?q=x%0D%0Ay#frag` and
`mailto:…?body=x%0D%0Ay#section` stay accepted.

The header comment, this document and the fixture table changed with the code.
No URL or book parser was added, no SDK/schema/host file was touched, and the
policy still returns metadata only.

## Cloud test evidence

Tested source **6fd6031c178ca567ad7a9ae7351b053aa23e45f3** on branch
`codex/reader-external-link-policy`, run **40136807836** attempt **1**.
All four jobs succeeded; the final HEAD of the branch is a later docs-only
`[skip ci]` commit and is not part of the tested source.

| platform | named checks | job |
| --- | --- | --- |
| Linux (ubuntu-22.04) | 37/37 pass | 120999938782 |
| Windows (windows-2022) | 37/37 pass | 120999938721 |
| macOS (macos-15) | 37/37 pass | 120999938532 |
| same-run artifact evidence | 3 ZIPs authenticated | 121000620042 |

Artifacts of that run (sha256 of the uploaded ZIP, retention until 2027-01-22T22:02:08Z):

| artifact | id | bytes | sha256 |
| --- | --- | --- | --- |
| reader-external-link-policy-Linux-40136807836-1 | 12577945550 | 426544 | 73f515acd1edc316c792d7f6131fab2f6dbee2ac0278a08323efbc87981873aa |
| reader-external-link-policy-Windows-40136807836-1 | 12577180979 | 862582 | 0df7d83f31a1b2385ae72a0eb5f5644ff7a9f47e202021d8a878346fb0afa6d4 |
| reader-external-link-policy-macOS-40136807836-1 | 12576959054 | 391458 | 0a72086ee3c991312a159710bba408ce4834e15f2dbf95fe43dbb48925cb6b7d |
| reader-external-link-policy-summary-40136807836-1 | 12577345813 | 864 | f3b27a2dbfa49b712199d1624609daaab043ed28ebfdd3e1e27a68ce485c5449 |

The evidence job downloaded each ZIP itself, recomputed its digest, rejected
altered report variants, and matched `report.json` to the installed library,
header and consumer bytes carried inside the same ZIP. It reported
`artifact evidence ok: 3 artifacts`.

Per platform: 144 default fixture cases, 7 custom-policy cases, 20 groups. The
`escape-boundary` group now holds 17 cases: the round-1 path/authority/fragment
control negatives, bad UTF-8 fragments and Unicode positives, plus
query-plus-bad-fragment (`?q=x#%0A`), query-CRLF-plus-fragment
(`?q=x%0D%0Ay#frag`), fragment-question-with-control (`#a?b%0A`), the literal
`#a?b` fragment, an external bad-UTF-8 fragment (`#%FF`) and a mailto CRLF body
with a fragment. The SDK hand-off still saw 6 authored entries with 4 INTERNAL
targets accepted by `exr_document_resolve` and the single NEEDS_HOST target
refused by it. The static symbol audit found no network, process or file
reference (110 symbols on Linux, 264 on Windows, 221 on macOS) and the negative
control was detected every time. The installed header digest is `3d61caf8…c622893a`
on all three platforms.

## Superseded rounds and retained failures

Earlier green rounds are retained in the validation record for their own source
and are **not** transferred:

- `b3a01821` / run **40134055434** (37 checks) closed round 1 but still carried
  the query/fragment boundary defect; artifacts 12576770797, 12576581157,
  12575853338, summary 12575763518.
- `e175a00f` / run **40123584995** (36 checks) was the first module acceptance;
  artifacts 12571723825, 12572047455, 12572544145, summary 12572590948. Its
  installed header digest `70deea67…` differs from the current `3d61caf8…`.

Retained original failures (kept, not rewritten):

- run **40122660917** (source ad378913): the C++ consumer was compiled with the
  wrong version macro names on every platform, so all three jobs failed;
  artifacts 12572355548, 12571393229, 12571918268, 12571519608.
- run **40122960979** (source 1df6dd3c): worker assertions and an MSVC `strcpy`
  refusal failed Linux and Windows; its still-queued macOS job was cancelled so
  the fixed run could get a runner and produced no evidence; artifacts
  12572206174 and 12572311188.

## Acceptance status

| item | status |
| --- | --- |
| module behaviour (37 named checks) | **accepted** on Linux, Windows and macOS from run 40136807836, both root review findings closed |
| installed C and C++ consumers | **accepted** (five consumers built from the install prefix only) |
| no network / process / file dependency | **static proof passed**, including a negative control |
| actual hosts (Windows, GTK, Android, Apple) | **not wired**; owned by root and the host owners |
| real device / emulator / performance / accessibility | **not in scope** of this package |
| root review against the merged common source | **not done**; integration is not claimed |

`docs/validation/reader-external-link-policy.json` carries the accepted record with the real run/attempt, jobs, artifacts, superseded rounds and retained failures above.
