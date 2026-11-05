# S19 host-feature link closure

The five optional packages (annotation import/export, font library, original
export, jump history, sync status view) are installed packages whose public
targets are static archives. A static archive is not a link closure: if a host
links them into a product DSO while the executable also carries the SDK, the
process ends up with two SDK implementations and, on some hosts, two product
catalog providers. This package supplies the narrow, checkable closure that lets
C09/C10/C11/D15 consume the five unchanged packages with exactly one of each.

## What ships

| Path | Content |
| --- | --- |
| `tools/reader_host_feature_link.cmake` | the CMake module: declare / attach / rpath / refusal rules |
| `apps/reader/host-feature-link/` | an installed package that installs that same module as `lib/cmake/EXReaderHostFeatureLink/EXReaderHostFeatureLink.cmake` (no library, no header, no copied code) |

Nothing else is added: no SDK target is relabelled, no static archive is removed
from a module interface, no module or store is reimplemented, and the installed
SDK provenance guard shipped by the font library and original export packages is
reused unchanged.

## Consumption (the only supported shape)

```cmake
find_package(EXReader 3.41.0 EXACT CONFIG REQUIRED COMPONENTS core library)
find_package(EXReaderProductCatalog 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderAnnotationImport 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderAnnotationExport 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderFontLibrary 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderOriginalExport 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderJumpHistory 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderSyncView 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderHostFeatureLink 1.0.0 EXACT CONFIG REQUIRED)

exr_reader_host_feature_link_declare(host_features
  SDK_PREFIX  "${EXR_SDK}"          # the one installed SDK
  SDK_VERSION "3.41.0"             # exact; 3.40.0 is the only other accepted pin
  SDK_LINK    shared               # shared = EXReader::exreader, static = EXReader::exr_core
  STORE_PREFIX "${EXR_STORE}"       # the one installed product catalog
  PACKAGE_PREFIXES ${EXR_MODULE_PREFIXES})   # where the five packages were installed

add_library(product_features SHARED features.cpp)          # the feature owner
exr_reader_host_feature_link_attach(product_features host_features ROLE FEATURE_DSO)

add_executable(product main.cpp)                            # the host process
exr_reader_host_feature_link_attach(product host_features
  ROLE HOST_EXECUTABLE HOST_OF product_features)
```

`declare()` produces an INTERFACE target whose link line is: the single SDK
provider first, then the six module targets, then the single product catalog
pair. The SDK provider is first because that order is what keeps a DSO from
pulling SDK archive members: every public SDK symbol a module needs is already
resolved by the shared provider when the archives are reached.

`attach()` has three roles:

* `FEATURE_DSO` — the artifact that owns the five modules and the product store.
  Only one per process. Requires `SDK_LINK shared`.
* `HOST_EXECUTABLE` — loads the DSO at run time. Must not link a module, the
  catalog, or a static SDK; the helper refuses if it does. It receives the one
  shared SDK (so its own SDK calls and the DSO's share one implementation) and
  the platform rpath for the installed layout (`$ORIGIN`, `@loader_path`).
* `STANDALONE_EXECUTABLE` — the whole closure in one executable; refused while a
  `FEATURE_DSO` exists, because that would be a second copy of the modules.

Configure-time refusals (all negative-tested in the Actions run):

| Graph | Message |
| --- | --- |
| DSO with `SDK_LINK static` | `a product DSO must not embed a second SDK implementation` |
| two `FEATURE_DSO` owners | `only one FEATURE_DSO may own the five modules` |
| host executable linking a module or the catalog | `the host executable links …` |
| module installed outside the declared prefixes | `resolved outside every declared install prefix` |
| standalone executable beside a feature DSO | `already owns the modules` |
| `add_subdirectory(apps/reader/store/native)` plus the installed catalog | `a private product store build is present` |
| SDK prefix or version disagreeing with the one actually found | `configured SDK is …` / `resolved outside …` |

## Evidence produced by the acceptance run

`tests/reader_wave3_s19/run.py` installs one SDK and the whole package chain into
one prefix, builds the DSO and the executable from installed packages only, then:

* drives one real business path per module (font import + SDK lease; original
  export with byte comparison; annotation export then import round trip through a
  real second store; jump history landing, peek, resolve and back; a real DAV
  session status capture with an outbox page);
* enumerates the process module set at run time and requires exactly one SDK
  image, one feature DSO, and one product store owner;
* compares the `exr_version()` pointer returned by the executable and by the DSO
  (equal only when both use the same SDK image), and reads the actual symbol
  tables (`nm`/`otool`, or the PE export/import directories on Windows) to prove
  the DSO defines no `exr_` symbol and the executable defines no module, catalog
  or SDK symbol;
* refuses the six mixed graphs above.


## Known integration requirements found by the S19 acceptance run

The third complete round (source `1423a0f0`) installed the reviewed SDK 3.41.0
and the whole package chain on all three runners, declared and attached the
closure, and compiled the five-module feature translation unit everywhere. The
product DSO then linked on macOS but not on Linux or Windows, for two different
real reasons. Both are properties of the *installed packages*, not of this
helper, and both must be handled before C09/C10/C11/D15 consume the closure.

1. **A DSO needs position-independent module archives.** The optional packages do
   not set `CMAKE_POSITION_INDEPENDENT_CODE` themselves (only the SDK top level
   does), so a default installed build of, for example, `EXReaderAnnotationImport`
   contains thread-local statics with `R_X86_64_TPOFF32` relocations. Linking
   that archive into a shared object fails with
   `relocation R_X86_64_TPOFF32 against '_ZN12_GLOBAL__N_16activeE' can not be
   used when making a shared object; recompile with -fPIC`.
   Install every package with `-DCMAKE_POSITION_INDEPENDENT_CODE=ON` when the
   consumer is a DSO. This changes no source, target or header.

2. **A Windows DLL cannot carry both the shared SDK import library and the SDK
   static archives.** MSVC still pulls the archive members that the modules
   reference and then reports `LNK2005` against `exreader.lib(exreader.dll)`
   (`exr_library_open`, `exr_document_open_memory`, `exr_anchor_create`,
   `exr_font_count`, `exr_version`, ...) and `LNK1169`. The module interfaces
   carry `EXReader::exr_core` as a real dependency, and this helper does not and
   must not remove it. On Windows the single-SDK closure therefore has to be the
   **static** one (`SDK_LINK static`, one SDK inside the DSO, the host executable
   linking no SDK at all); the shared-SDK profile stays valid on ELF and Mach-O,
   where the shared provider is processed first and the archives are not pulled.

Both facts were observed, not inferred: `libreader_host_features.dylib` and
`reader-host-probe` linked and three of the six mixed graphs were refused in the
same run that produced the Linux and Windows link errors.

## Boundaries

* This package is a link-closure package, not a UI package: no host窗口, no
  preferences, no More menu. C09/C10/C11/D15 own the real UI.
* Only the legacy (default) module family is exercised: annotation import/export
  0.1.0, jump history 0.1.0, sync view 0.1.0 over reading-state 0.1.0 and session
  0.1.0. The raw selector family is not part of this closure.
* The forty-two S14 negative verifier cases, the S15 graph controls and the S17
  mixed-profile matrix are not re-run here; they stay with their own packages.
* No physical device, no packaged installer, no performance claim.
