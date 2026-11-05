# Library health (optional package)

Read-only health scan of one product catalog against one local SDK library.
See [docs/READER-LIBRARY-HEALTH.md](../../../docs/READER-LIBRARY-HEALTH.md) for
the contract, limits, threads and cancellation rules, and for the cloud
validation that publishes this package.

The package links only the frozen public SDK `library` component and the
product catalog provider. It never writes, repairs, downloads or re-imports.

Build against installed packages only:

```text
cmake -S apps/reader/library-health -B build/library-health \
  -DEXR_SDK=<sdk-stage> -DCMAKE_PREFIX_PATH=<catalog-stage> \
  -DCMAKE_INSTALL_PREFIX=<health-stage>
cmake --build build/library-health
cmake --install build/library-health
```

Cloud validation compiles the installed C and C++ consumers in
`tests/reader_library_health/consumer` from the install prefixes only.
