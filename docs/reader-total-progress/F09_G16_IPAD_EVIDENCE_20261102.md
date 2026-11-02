# F09 iPad single production evidence candidate

Base: 6293c9d6d5ccf968d36bbf2f3790d166da275c90.
Branch: audit/f09-g16-ipad-evidence-20261102.
This package adds only three files. The successful iPhone workflow, runner,
Swift collector, generated-project overlay, original tests, product, and SDK
remain byte-for-byte unchanged.

The runner derives from the successful iPhone collector, changing only device
selection to iPad mini (A17 Pro), output labels, and fixed-base three-new-path
scope. It uses the same iOS targets, pinned simulator SDK, production settings,
single-case invocation, timeouts, and first-failure stop conditions.

Budget: one commit/push, one macos-15 job capped at 45 minutes, normal-size
single collector case once. No automatic retry or device substitution.
The exact available device and runtime are recorded, not inferred from history.

Evidence: library.empty name/count and reader.state absence in the current
application's XCUI-queryable descendants at their respective anchored states.
A shared session and completed test bind the raw log/records to actual build
settings and built/installed-before/installed-after program and plist hashes.
The test runner configuration, registration readback and single installation
retain the already reviewed identity checks.

This is not VoiceOver evidence, OS-wide AX completeness, three-platform
integration, or a formal legacy-G16 gate result. acceptance_eligible remains
false. Historical failures and original contract remain unchanged. Contract
owner approval and formal integration are separate; this package does not
transfer Apple production ownership or alter the official ledger.
