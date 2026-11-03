# V · version identity inventory · 2026-11-03

Branch: codex/sdk-version-single-source-20261103. Base: 95100501eeef9c6325be8b3882aa400c99cf000f.

Owner target: EXR_SDK_VERSION=3.42.0 from cmake/versions.cmake, ABI epoch 1. Component versions remain independent. V must precede any refreeze candidate; no refreeze is authorized.

scan-before.json is a portable file/line/value inventory across tracked tests, workflows, tools and examples. It contains 816 occurrences (542 of 3.41.0, 262 of 3.40.0, 12 of 3.42.0), including historical fixtures and negative cases. It is not a list of 816 current-version defects.

Pending scope clarification: preserve explicitly identified historical SDK compatibility fixtures and deliberate wrong-version rejection cases, while current SDK assertions read the source of truth. Examples requiring this distinction include tests/reader_sdk_version/run.py (two pinned historical SDKs and a future-version rejection) and tests/apple_host/record_compatibility/ParserPolicyCheck.java (old/current/future admission cases). Component core version 3.40.0 must remain independent.

No production, workflow, version declaration or test has been modified yet. No consistency-check acceptance or negative-case result is claimed by this inventory.
