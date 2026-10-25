# Native owner repairs

Baseline: `96270a2b478b673eb45b7e2467e2e2acb6b64a88`. Source-only candidate;
not compiled or tested yet. All execution and artifact processing must occur
in Actions. Frozen SDK, seven raw packages, schemas and budgets stay unchanged.

The delivered D08/D09/D12 audit records identify these native-owner defects;
the relevant current Windows files match their audited target bytes. D08
`30158c44`, D09 `8f55aa39`, D12 `df78d4f5` remain failed audits, not prior passes.

- Windows search/navigation/records/preferences close share one focus helper
  selecting a visible, enabled page or shelf. An already-loaded book no longer
  causes shelf dialog dismissal to focus a hidden reading page.
- Successful resolved GO/layout publication arms the existing pending selection
  with the accepted current book and frame part before applying its byte range.
  Independent FOUND and frame bounds remain mandatory; no old hint fallback.
- The native records owner decodes SAFE progress solely to report whether a
  location exists. Open and annotation Edit require a usable location; deletion
  semantics remain unchanged. Genuine NULL wire is retained without conversion
  to allocated empty text. The added field belongs only to the app-private C
  owner response compiled with its caller; no public SDK/module ABI changes.
- Initial Windows outer bounds and minimum tracking bounds are capped at the
  actual monitor work area. No DPI/contrast acceptance is inferred from this.
- GTK records opening gives its Close control focus after the initial async
  request disables the list. The shared entry covers menu and keyboard callers.

Cloud regression requirements: actual native keyboard/modal descendant focus,
default and small work-area bounds, independently resolved real received
TXT/EPUB/PDF highlights, genuine NULL Open/Edit disabled and no state changes,
and keyboard/menu GTK records focus. Build default/OFF and raw profiles and
retain original complete regression business assertions. Source wrappers must
describe their new source policy explicitly; do not spoof old guards or event
identities. Actual binaries, original producer ZIPs, reports, expiry, source,
run/attempt and negative controls must be authenticated. At most three full
root rounds; preserve every failed or missing scope.
