# Windows and GTK SDK 3.42 common candidate

This candidate starts at GTK source `ef3356c30046d0646cf1cc6d37b53fe942121e38`
(run 40650531318, attempt 1). It adapts the Windows F06 identity fix from
`90c8773fe863e39157ac6e4f9a82a2d66d84cd93` (run 40653146033, attempt 1),
whose baseline is `08eb7f1fdf09fca815a40400634354ef393f3225`. The shared
SDK implementation originated at `7271829a829bfa6aaa47b73077c493f71af27ad3`.
Prior runs are historical evidence only; both gates must pass on this candidate's
own SHA. Original assertions and exact SDK matching remain in force. The F06
Linux adapter itself still defaults to 3.41; the GTK gate explicitly injects
3.42, and the other four F06 producers have not been validated at 3.42 here.

The Windows workflow also retains the raw selfcheck report, image and application
log. Desktop archive entry checks cover extracted executable identity and native
dependencies; they do not substitute for a complete GUI regression or release.
