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
runs each consumer, and writes `report.json` with 36 named outcomes. `check_artifacts.py`
then authenticates the three same-run ZIPs through the GitHub API, re-computes
their digests, and compares the report against the installed library, header and
consumer bytes inside the same ZIP.

## Acceptance status

| item | status |
| --- | --- |
| module behaviour (36 named checks) | cloud test pending |
| installed C and C++ consumers | cloud test pending |
| no network / process / file dependency | static proof pending (audit + negative control) |
| actual hosts (Windows, GTK, Android, Apple) | **not wired**; owned by root and the host owners |
| real device / emulator / performance / accessibility | **not in scope** of this package |

`docs/validation/reader-external-link-policy.json` starts with `accepted=false` and is
filled only from real, same-run artifact evidence.
