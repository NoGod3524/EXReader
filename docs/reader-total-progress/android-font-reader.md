# Android reader font library: independent candidate evidence

Source: `41870a040bb6ff995a7adddc13756880ada8c731`.
[Run 40582860559, attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40582860559) completed successfully on the real Android host in an API 34 x86_64 emulator.

The reader More menu exposes the existing local font panel. The original same-run
C11, navigation and reading suites passed, as did three new checks: actual font
import/selection and changed rendered pixels on reopening; bad-font failure on a
noninitial page preserving frame, anchor, selected font and active lease; and
lease release plus position preservation on reopening.

The original artifact `12772457377` has 164193268 bytes and SHA-256
`9a4a1120a3a20d6bab7b6d31febaa9a2ab4411e1ba10189ffed9380669880c45`.
The fixed-catalog audit checks its identity and reads the three named passing
checks from the original report in GitHub Actions.

Framework activity results are supplied by test stubs; the run does not cover
real DocumentsUI, a physical device, or TalkBack. Font application takes effect
on the next open. Unified-source delivery is tracked separately.
