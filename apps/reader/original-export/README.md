# EXReaderOriginalExport 0.1.0

Independent opt-in static C ABI package for exporting the exact original file of
an explicitly selected book. It is never added to the SDK, the default reading
configuration, a host, or the existing sideload exporter.

## Install graph

The package consumes only an installed EXReader SDK through its public CMake
package and public headers:

```
cmake -S apps/reader/original-export -B build/original-export -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DEXR_SDK=/path/to/installed/exreader \
  -DEXR_SDK_VERSION=3.41.0 \
  -DCMAKE_INSTALL_PREFIX=/path/to/prefix
cmake --build build/original-export
cmake --install build/original-export
```

`EXR_SDK_VERSION` is an exact pin and accepts only `3.40.0` or `3.41.0`:

* The default is `3.40.0` (the frozen SDK), so existing hosts keep their
  behavior and a 3.41-only install is refused by default.
* `3.41.0` is the approved candidate and must be requested explicitly.
* Any other value fails during configure with
  `Unsupported exact reader SDK version: <value>`.

The installed package records the pin it was built against:

```
find_dependency(EXReader <EXR_SDK_VERSION> EXACT CONFIG COMPONENTS library)
```

so a consumer cannot mix an SDK graph with a module archive built for a
different exact SDK. Downstream projects use:

```
find_package(EXReaderOriginalExport 0.1.0 EXACT CONFIG REQUIRED)
target_link_libraries(app PRIVATE EXReaderOriginalExport::reader_original_export)
```

## What the module does

See `docs/READER-ORIGINAL-EXPORT.md` in the module's own package record for the
full contract. In short: the host lends its single `exr_library` and owner gate;
`roe_run` preflights 1–100 explicit book IDs, opens each original through the
public chunked `exr_library_source` API (the same primitive the unchanged
sideload exporter uses), streams it in 64 KiB reads while hashing, flushes and
reads back the staged file, and publishes it without replacing any target.
Temporary paths, cleanup receipts and per-item status are reported to the host.

The source and header of this package are byte-identical to the module's fixed
commit; only the install configuration carries the explicit 3.41.0 opt-in.

## License

MIT, as declared by the SPDX headers in every file of this package.
