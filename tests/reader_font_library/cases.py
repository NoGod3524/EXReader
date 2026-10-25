# SPDX-License-Identifier: MIT
"""Fixed acceptance cases; reports may neither omit nor invent cases."""
COMMON = [
 'unrelated-private-directory-file-preserved', 'installed-c-abi-sdk340', 'empty-library', 'ttf-import-content-identity',
 'deduplicate-preserves-record', 'find-list-bounds', 'sdk-glyph-shape-layout',
 'leased-remove-close-busy', 'wrong-thread-preserves-owner-and-lease',
 'bounded-live-lease-count', 'otf-sdk-validation', 'ttc-explicit-face-and-invalid-face',
 'manifest-close-reopen', 'same-process-exclusive-directory-lock',
 'display-name-unicode-path-injection-bounds', 'unicode-selected-path-and-display',
 'bad-and-truncated-preserve-library', 'nonregular-source-rejected',
 'bounded-source-short-reads-and-hash', 'source-contract-snapshot-bounds', 'underreported-source-rejected',
 'invalid-source-return-and-exception-contained', 'advertised-font-hard-limit-before-read',
 'stored-hash-tampering-rejected', 'source-truncation-rejected', 'source-midstream-change-rejected',
 'callback-reentry-rejected', 'cancel-each-stage-retry-preserves-old',
 'selected-file-post-open-change-rejected', 'font-exact-byte-boundary',
 'font-over-byte-boundary', 'directory-entry-limit-dedupe-at-capacity',
 'quota-deduplication-no-oversized-temporary', 'reopen-lower-budget-classified-limit',
 'directory-byte-limit-preserves-old', 'hard-limits-reject-oversized-config',
 'explicit-remove-and-not-found', 'selected-original-never-removed',
 'content-path-conflict-no-overwrite', 'manifest-version-corrupt-missing-classification',
 'crash-copy-recovery', 'crash-validated-recovery', 'crash-file-published-recovery',
 'crash-committed-recovery', 'cross-process-lock-and-kill-release',
 'recomputed-original-font-hashes', 'installed-binary-and-package-identities',
 'default-off-no-library', 'frozen-installed-font-header',
]
POSIX = ['posix-source-and-directory-symlinks-rejected', 'posix-real-short-write-preserves-old']
WINDOWS = ['windows-removal-commit-uncertain-recovery', 'windows-junction-rejected', 'windows-locked-manifest-publish-failure-preserves-old']
NEGATIVE = ['wrong-source','wrong-run','wrong-attempt','unfinished-job','failed-job','duplicate-job',
 'missing-artifact','duplicate-artifact-name','duplicate-artifact-id','empty-artifact','expired-artifact',
 'expired-timestamp','wrong-artifact-source','wrong-artifact-run','wrong-zip-size','wrong-zip-digest',
 'duplicate-zip-member','duplicate-json-key','missing-case','extra-case','duplicate-case',
 'missing-original-module','altered-binary','altered-license','wrong-report-source',
 'wrong-report-attempt','wrong-report-run','failed-report','wrong-platform','unbound-module-source']
