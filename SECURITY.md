# Security policy

EXReader parses untrusted documents (EPUB, PDF, PPT/PPTX, DOCX, MOBI/KF8, CBZ, 7z,
dictionaries, audio). Memory-safety bugs, unbounded work or memory, and path
traversal in these parsers are security issues.

## Reporting a vulnerability

Please report privately through GitHub's
[private vulnerability reporting](https://github.com/NoGod3524/EXReader/security/advisories/new)
instead of a public issue. Include the EXReader version (`VERSION`), platform and
compiler, and a minimal input file or the steps that reproduce the problem.

You can expect an acknowledgement within 7 days. Fixes land on `main` with a
regression test; the advisory is published once a fixed build is available.

## Supported versions

Only the latest `main` is supported. Preview releases are not patched separately.
