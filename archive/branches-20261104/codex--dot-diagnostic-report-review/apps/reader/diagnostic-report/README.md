# EXReader diagnostic report (optional module)

User-triggered, bounded diagnostic export for import/sync/reading failures. The
host fills a closed set of enumerators, counters and error counts; the library
renders canonical JSON (format `exreader-diagnostic-report`, format version 1)
and a short plain-text summary, and can publish either to a new file.

The full contract (privacy set, ownership, threads, errors, cancellation, commit
boundary, hard limits) is in `include/reader_diagnostic_report.h` and
`docs/READER-DIAGNOSTIC-REPORT.md`.

    #include "reader_diagnostic_report.h"

    reader_diag_input input = reader_diag_input_defaults();
    input.app_version = "1.4.2";
    input.platform = READER_DIAG_PLATFORM_WINDOWS;
    input.operation = READER_DIAG_OPERATION_SYNC;
    reader_diag_report *report = NULL;
    if (reader_diag_report_build(&input, NULL, &report, NULL) == READER_DIAG_OK) {
      const char *json = reader_diag_report_json(report, NULL);
      reader_diag_report_write(report, "report.json", NULL, NULL);
      reader_diag_report_free(report);
    }

Build and install as an independent CMake project:

    cmake -S apps/reader/diagnostic-report -B build/diagnostic-report \
      -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=<prefix>
    cmake --build build/diagnostic-report
    cmake --install build/diagnostic-report

Consumers then use `find_package(EXReaderDiagnosticReport 0.1.0 CONFIG REQUIRED)`
and link `EXReaderDiagnosticReport::reader_diagnostic_report`.

The library performs no I/O other than the single publish step, never reads a
file, environment variable or clock, never uploads anything and never replaces an
existing file. `tests/reader_diagnostic_report/` contains the installed C and C++
consumers, the test-hook worker and the cloud-only acceptance checker.
