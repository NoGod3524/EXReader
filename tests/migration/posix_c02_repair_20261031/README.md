# POSIX repair helper component checks

This standalone C consumer compiles the scanner/store sources directly and links
the separately installed frozen ABI2 coordinator. It does not link the unfinished
repair guard or the SDK, and does not change the original 55 admission scenarios.

Run only in GitHub Actions, as a nonroot runner:

~~~sh
cmake -S tests/migration/posix_c02_repair_20261031 -B build/repair-helpers \
  -DWH_PREFIX="$PWD/stage-abi2" -DSOURCE_SHA="$GITHUB_SHA"
cmake --build build/repair-helpers --parallel 4
python tests/migration/posix_c02_repair_20261031/run.py \
  --tool build/repair-helpers/posix-c02-repair-helpers-check \
  --output evidence/repair-helpers
~~~

Select GCC/Clang using the normal CMake compiler setting. All 30 named scenarios
have independent counts. Every possible partial B/C length (1..367) and partial
head-record length (1..271) is checked both against the exact canonical next bytes
and a changed final tail byte. Complete contradictions cannot become a shorter
valid prefix. ACK296/FLOOR352/head relationships and the single interrupted
append constraints are checked separately.

Native store cases retain a real FIFO, sources, archives, malformed wrappers, same-byte
replacement objects, failed publication temporaries, hardlinks, symlinks and ACL
fixtures. The runner records actual fd-derived IDs and raw file SHA256, and
independently decodes wrapper112 with Python. A component result always reports
actual_sdk=false and production_repair=false; real owner recovery has its own
qualification. Exclude native/store/fifo-plan from artifact upload: its actual fd
metadata is retained in the observation JSON, and the FIFO remains on the runner.
