# Reader and migration transaction composition preparation

This branch combines reader source
`36fb8db3c088d665f87aac407f8e3739fa73e0f0` with transaction SDK candidate
`8357eafa28423a7ab93ba08b823af80f01ad1505`. The merge commit is
`dafd61da35c5e38d17900b01d150f6def18adeb5`; Git reports no merge conflicts.
This is a preparation candidate: no build, tests, migrated user data or host
integration have been performed on this combination.

The migration candidate is SDK 3.42.0. Integration must address these exact
version boundaries instead of silently substituting a 3.41 build:

- `apps/reader/desktop/CMakeLists.txt`, search and other optional package
  CMake files accept explicit 3.40 or 3.41 only and use exact package discovery.
  Inspect each module and carry the exact installed SDK version through its
  build and exported package dependencies.
- `examples/android/app/src/main/cpp/CMakeLists.txt` permits the page-theme
  path only with 3.41. `ReflowSession.themeSnapshot` independently rejects
  frames whose SDK string is not exactly 3.41. The Gradle SDK setting is
  configurable but defaults to 3.41. Update the explicit candidate route and
  test both build and actual theme rendering before granting 3.42.
- `examples/apple/HostReadingRecords.swift` and
  `apps/reader/desktop/windows_records_owner.cpp` explicitly allow a 3.41
  decoder to read selected 3.40/3.41 parser tags. Adding 3.42 requires a
  deliberate compatibility decision and real old-wire resolution checks;
  do not rewrite recorded wire metadata or infer compatibility from a version
  string alone. Review the Android reading parser policy and other host
  selectors for the same issue.
- The host lifecycle must drain and close readers and owners before invoking
  migration, handle failure without losing the original, then reopen and
  refresh with the upgraded SDK. Packaging and old/new migrator coordination
  remain separate required work.

The 3.42 candidate has not passed its unchanged historical migration gate:
[40636401201](https://github.com/NoGod3524/EXReader/actions/runs/40636401201)
records 52/65 candidate scenarios on Linux and Windows, and macOS remains
queued. The Android common-source validation
[40640180824](https://github.com/NoGod3524/EXReader/actions/runs/40640180824)
was running when this note was created. Do not treat that source or any
individual upstream result as acceptance of this merge.
