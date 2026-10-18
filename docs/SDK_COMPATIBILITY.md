# EXReader SDK compatibility

ABI epoch **1** was introduced in development step **S091** (original build
**0.91.0**, commit `7dc8d8a`), now part of milestone **0.18.0**. `EXR_ABI_VERSION` identifies the header's epoch;
`exr_abi_version()` identifies the loaded library's epoch. `EXR_VERSION` and
`exr_version()` identify the release. Epoch 1 does not retroactively classify older
SDK binaries that did not export the ABI query.

## Binary contract

Within one epoch, existing exported C symbols, calling conventions, enum numeric
values, public record sizes/alignment/member offsets, callback signatures and
ownership contracts remain compatible on the same operating system, architecture
and compiler ABI. Removing symbols or changing those layouts requires a new epoch.
Adding functions does not. Optional build features retain their public symbols;
for example, `exr_text_index_available()` reports whether FTS indexing is enabled.
A host using new functions also requires the release
that first provides them; an epoch alone does not imply that every later symbol
exists in an older library.

Use the platform's normal C calling convention, natural structure alignment and
normal enum representation. Do not compile the public header under packing or
short-enum options. C++ callers use the header's `extern "C"` declarations and keep
exceptions inside their own callbacks. `size_t` and pointers are native-width;
public structs are not an on-disk or network serialization format.

Existing array-element records cannot gain fields within an epoch, including
fields appended at the end: that would change their stride for older callers.
New array layouts require new types and entry points. Inputs explicitly carrying
`struct_size` may grow by preserving the original prefix. Zero-initialize them,
set the size of the header's actual type and leave unused fields zero. A library
rejects unsupported nonzero extensions instead of silently interpreting them.
The original fixed-provider prefix remains a tested consumer even though later
headers append optional text, metadata and annotation callbacks.

The 0.18 development PDF password interface appends `pdf_password`,
`pdf_password_size` and `pdf_security` to `exr_fixed_open_options`; the original
prefix remains accepted. Recompile hosts that need these fields. Error values
0-9 retain their numbers; 10 is `EXR_PASSWORD`, 11 is `EXR_UNSUPPORTED`.
`exr_pdf_security_info` is a new output type with its own `struct_size`.
`exr_pdf_crypto_available()` reports the optional build component. The Swift
initializer adds a defaulted `password: Data?` parameter, and Java retains its
original constructors while adding password-byte overloads and security snapshots.
Rebuild JNI together with its matching Java wrapper. Windows MinGW now installs
`exreader_jni.dll` with the filename expected by `System.loadLibrary`.

The later 0.18 table-layout update defaults to content-driven auto widths,
including shrink-to-content for tables without a definite width. Existing table
page counts and coordinates may therefore change, while source text positions
and public ABI layouts retain their contract. Use standard
`table {table-layout:fixed;width:100%}` CSS for the old full-width equal-column
presentation; unnamed host nodes can carry that inline style directly. The old
0.10 pixel goldens explicitly request this fixed presentation, while independent
auto-width vectors, random tables and checkpoint tests validate the new default.

Cell alignment now uses the CSS baseline initial value and HTML table-group
defaults, with top/middle/bottom/baseline support. Different font sizes/paddings
and spanning cells may therefore change row heights or content coordinates.
Request `vertical-align:top` on cells to preserve the old top-aligned presentation;
the legacy pixel-golden CSS does so explicitly. The first-line/row baseline
metadata remains private; public array strides and ABI epoch stay unchanged.

## Ownership and execution

Opaque handles are released with their matching `*_free`/close function. Allocated
arrays and nested records use their documented typed free routine. Plain returned
allocations use `exr_free`; never free SDK allocations through a host CRT. Borrowed
views expire with their owning handle. Copy a view when it must outlive its owner.
The API documentation specifies retained font, publication/archive and layout
relationships; those rules are part of the contract.

The engine invokes callbacks synchronously and creates no worker threads. Serialize
calls and lifetime changes for a shared mutable handle or shared archive graph.
Callbacks must not free/reenter the active object. Independent object graphs can
run independently. The atomic unique-import operation additionally protects its
lookup/insert transaction; it does not establish unrestricted thread safety for
all book-library operations.

UTF-8 byte offsets in normalized text, raw XML UTF-16 CFI offsets and fixed-page
coordinates are distinct units. Persist portable selectors/CFIs rather than raw
public structs. Rendering and normalization algorithms may improve across releases;
an ABI epoch describes the binary contract, not pixel-identical output. SQLite
schema versions and supported input-format subsets are tracked separately.

## CMake consumers

An installed SDK contains a relocatable config package:

```cmake
find_package(EXReader 0.18.0 EXACT CONFIG REQUIRED)
target_link_libraries(my_host PRIVATE EXReader::exreader)
```

The version renumbering keeps ABI epoch 1 and SQLite schema 6 unchanged. Update
old CMake requirements such as 0.91/0.96 to the new milestone number. Use EXACT
when selecting this SDK: older development packages numbered 0.91–0.100 sort
above 0.18 and must not be selected as supposedly newer compatible packages.
Historical versions are compared through the [version map](VERSIONING.md) and
commit IDs, rather than numeric ordering across the renumbering.

Set `CMAKE_PREFIX_PATH` or `EXReader_DIR` to the selected platform SDK. The imported
target carries its include path and actual platform import/shared-library path;
FreeType, Expat, miniz, SQLite and image decoder build directories are not required
by the consumer. `EXReader_VERSION` and `EXReader_ABI_VERSION` describe that package.
The host bundles the corresponding shared library using its platform's loader
rules. Keep SDK/runtime releases paired unless the host deliberately checks its
required release and ABI at startup.

`examples/compat.c` compares package, header and loaded runtime values. All installed
host examples now use the imported target; desktop CI configures, builds and runs
them independently from the engine source build. Windows copies the installed DLL
next to the examples. Swift and JNI remain separate optional adapters over the
same C contract.
