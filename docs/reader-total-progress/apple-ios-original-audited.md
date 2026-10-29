# iOS original export independent audit

Independent [40910291131](https://github.com/NoGod3524/EXReader/actions/runs/40910291131) reread the exact original archives from [40905868673](https://github.com/NoGod3524/EXReader/actions/runs/40905868673), source `127cdb7c62772fd293c10cc032547c28904bd1c2`. Both iPhone and iPad simulator native `testSystemFolderSave()` cases passed. Source and system-saved EPUBs are equal, 7,724 bytes, SHA-256 `0c54c6c969cb720875557d8f877d0733cc65dd1e80d74d098fb18ba65bf42bdb`.

The audit authenticates run, attempt, source, producer job, original ZIP size and hash, native XCTest result, and both files. The original artifacts do not retain application binaries; program hashes remain original producer records. These are SDK 3.41 simulator results, not SDK 3.42, physical-device or common-source product acceptance. Earlier picker failures remain unchanged.
