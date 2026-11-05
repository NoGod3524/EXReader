# Branch file archive · 2026-11-04

Base: `26dac7335b844127c38d4084e7c5cc081e464ee5`.

The owner selected file-content custody in place of format-patch or bundles. For each branch, the selected paths are the output of:

```sh
git diff --name-only --diff-filter=d 26dac7335b844127c38d4084e7c5cc081e464ee5...<branch>
```

Each selected file contains the exact raw blob bytes at `tip_sha:path`. Export uses binary-safe `git cat-file --batch`, equivalent to redirecting `git cat-file -p <tip>:<path>` for each file. Every exported file was read back and checked with `git hash-object --no-filters`; three deterministic sample branches additionally compare `git rev-parse <tip>:<path>`.

`MANIFEST.csv` has one row per branch; `files` and `bytes` count exported file copies, and `file_list` is a JSON array of source paths. The branch directory replaces slashes with `--`. This archive stores non-deleted file contents, not commit history.

No archive tag is created. Main remains frozen pending PR #42.
