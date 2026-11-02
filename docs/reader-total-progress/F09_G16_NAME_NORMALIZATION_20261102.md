# F09 candidate naming normalization
Base: 5737413cb60ea3205bef1e4d28005181fd3998d0.
Only candidate adapter naming changes. Legacy collector, contract, product, SDK,
original 12 controls, provenance requirements, and formal acceptance stay unchanged.

The legacy collector ax_name (audit_collect.py 127-133) returns the original
non-whitespace string label, else the string value, else empty string.
name_equals (185-187) compares both strings after strip. The new candidate
module mirrors these rules. Raw label/value fields override normalized name;
existing name-only synthetic input remains supported. No real AX normalization,
receipt creation, or replay is performed by this package.

Original 12 synthetic controls run unchanged, plus exactly 8 additional controls:
label priority; empty-label value fallback; whitespace-label fallback;
non-string-label fallback; non-string/missing value; trimmed equality;
raw fields resist forged name; normalization cannot repair identity mismatch.
One Ubuntu job at most 10 minutes. No build, device run, archive download, or retry.

Evidence inventory exception: generated artifact 13134519939, 237551 bytes,
SHA256 7f640a3a08f5155df94f85d6f6bb37f5545e1492411a73a0aa9f9969ea314b39.
Only report.json member inventory was read after verification. Across 3311
original members no .app path or named EXReaderHost/program/executable member
was found; the five Info.plist entries belong to xcresult bundles, not host apps.
Opaque xcresult data were not opened or interpreted. Reported program hashes
remain assertions, not independently rehashed host binaries. SDK is not a host
program identity substitute.

candidate-only; acceptance_eligible=false; legacy_rules_evaluated=false.
No historical six blocking results are replaced. Bounded raw AX records,
program binding gaps, and missing iOS VoiceOver remain separately tracked.
