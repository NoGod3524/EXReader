# SPDX-License-Identifier: MIT
"""Fixed acceptance cases for S14; reports may neither omit nor invent cases.

ORIGINAL_* are the unmodified named cases of the reused font library at
1563f4abb85ccd28c3a0aae3e9913f4330536215. S14_* are the additional cases this
package adds for the explicit SDK3.41 selection; no original name changes.
"""
ORIGINAL_COMMON = [
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
ORIGINAL_POSIX = ['posix-source-and-directory-symlinks-rejected', 'posix-real-short-write-preserves-old']
ORIGINAL_WINDOWS = ['windows-removal-commit-uncertain-recovery', 'windows-junction-rejected',
                    'windows-locked-manifest-publish-failure-preserves-old']

# Emitted by the reused C++ suite in probe.cpp mode "s14".
S14_COMMON = ['s14-unicode-path-duplicate-import', 's14-invalid-font-preserves-selected-set',
              's14-reopen-unicode-directory-identity']
# Judged by the S14 harness, never by the C++ suite.
S14_HARNESS = ['s14-installed-sdk-version-selected', 's14-installed-package-binds-exact-sdk',
               's14-wrong-sdk-selection-rejected', 's14-invalid-sdk-selection-rejected',
               's14-single-sdk-provider', 's14-reuses-pinned-module-bytes']

# Cases the Python harness owns in the original package.
HARNESS_COMMON = ['installed-c-abi-sdk340', 'crash-copy-recovery',
 'crash-validated-recovery', 'crash-file-published-recovery', 'crash-committed-recovery',
 'cross-process-lock-and-kill-release', 'recomputed-original-font-hashes',
 'installed-binary-and-package-identities', 'default-off-no-library', 'frozen-installed-font-header']

# Native case set the reused C++ suite must print, per platform.
NATIVE_COMMON = [name for name in ORIGINAL_COMMON if name not in HARNESS_COMMON]
NATIVE_POSIX = ['posix-source-and-directory-symlinks-rejected']

# Command roles and their expected success, per platform.
ROLES_COMMON = {'c-consumer': True, 'suite': True, 's14': True, 'list': True, 'status': True,
                'import': True, 'configure-invalid-sdk': False, 'configure-wrong-sdk': False,
                'consumer-wrong-sdk': False}
ROLES_POSIX = {'write-full': True}
ROLES_WINDOWS = {'locked-manifest': False}

NEGATIVE = ['wrong-source','wrong-run','wrong-attempt','unfinished-job','failed-job','duplicate-job',
 'missing-artifact','duplicate-artifact-name','duplicate-artifact-id','empty-artifact','expired-artifact',
 'expired-timestamp','wrong-artifact-source','wrong-artifact-run','wrong-zip-size','wrong-zip-digest',
 'duplicate-zip-member','duplicate-json-key','missing-case','extra-case','duplicate-case',
 'missing-original-module','altered-binary','altered-license','wrong-report-source',
 'wrong-report-attempt','wrong-report-run','failed-report','wrong-platform','unbound-module-source',
 'altered-native-log','forged-native-case','missing-native-command','missing-termination','zero-termination-exit',
 'wrong-sdk-version','wrong-sdk-tag','altered-installed-package-config','wrong-package-sdk-binding',
 'missing-command-role','unexpected-command-failure','reused-module-differs']
