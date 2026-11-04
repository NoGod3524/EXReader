# Corpus consumer version repair — 2026-11-04

Previous core run 41774219995 failed only in corpus: the active consumer required exact 3.41.0 while the installed package was 3.42.0. Native/protocol/profiles/platforms passed.

- tests/reading_corpus/CMakeLists.txt:3 now uses find_package(EXReader CONFIG REQUIRED COMPONENTS core pdf), consuming the installed package without a version pin.
- tools/check_version_consistency.py scans all CMakeLists.txt, .cmake and .cmake.in files for numeric find_package(EXReader <literal>) versions, including multiline/quoted values. A mismatched literal must match an existing exact, validated evidence exception; otherwise it reports file:line, actual and source version, with the instruction “改为读取安装包 version file，或登记豁免”.
- The same new rule found one unregistered sibling pin in extras/ocr/CMakeLists.txt:3 (3.40.0 EXACT); it now also consumes the installed package without a version pin. No component version or SDK version changed.
- Removed only the now-stale corpus line-3 waiver from tools/version_literal_exceptions.json. No retained historical fixture literal was upgraded or modified; no new frozen exception was created. The valid exception count is 587 (previously 588).
- The existing CI --self-test now deliberately restores the consumer to the previous SDK minor version (currently 3.41.0), requires exit 1 with the exact location/source version/guidance, and restores source bytes in finally.

Local validation: tools/check_version_consistency.py --self-test passed (including original project-version control and new consumer-version control); tests/check_version_consistency.py passed all seven evidence refusal cases and generated-byte drift checks. Full output: version-negative.txt and version-regression.txt. Existing tests/check_benchmark.py remains unchanged.

The previous native milestone and one-time core probe evidence are integrated from evidence commit 6db1181a in the same repair PR. Repair commits use [skip ci]; after integration, exactly one temporary comment PR will trigger the only new core run. It will be closed without merging and its branch deleted after the terminal results are recorded.
