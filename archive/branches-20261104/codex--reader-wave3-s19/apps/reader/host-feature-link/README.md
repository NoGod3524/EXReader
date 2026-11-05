# EXReaderHostFeatureLink

Installed CMake host-link package for the five reviewed optional reader
packages. It installs exactly one module,
`lib/cmake/EXReaderHostFeatureLink/EXReaderHostFeatureLink.cmake` (a copy of
`tools/reader_host_feature_link.cmake`), and adds no target, header, library or
provider of its own.

Consumers call `exr_reader_host_feature_link_declare()` and
`exr_reader_host_feature_link_attach()` after importing the installed SDK, the
installed product catalog and the five installed packages. The helper refuses
every graph that would put a second SDK implementation or a second product store
provider into one process.

Full usage, the refusal matrix and the acceptance evidence are in
`docs/reader-wave3-s19/README.md`.
