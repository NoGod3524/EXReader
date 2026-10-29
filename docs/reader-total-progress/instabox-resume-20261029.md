# InstaBox continuation — 2026-10-29

User requested that root coordination and source work continue on the existing InstaBox.

- Machine: `agent-browser-mol0`, ID `m_agqxv2s72g5vwdtsifu5cnmml4`.
- Official CLI account login succeeded; observed state is running and runtime.ready=true.
- Original `/data/workspace/exreader-composition` remains clean at `2f215f5793a7344d22db350276ba9f8a07abe86f` and is preserved.
- New product worktree: `/data/workspace/exreader-resume-20261029`, branch `codex/instabox-integration-20261029`, initially exact common source `343bb94eb6513beaf5b344e7828342f6602a3b7b`.
- New independent evidence worktree: `/data/workspace/exreader-evidence-resume-20261029`, branch `codex/instabox-evidence-20261029`, initially root audit `b1b8a50d`.
- Product destination stays `codex/public-product-resume-20261029`; audit destination stays `codex/handoff-evidence-resume-20261029`. Never push the default branch or create a PR/tag/Release.
- Both local and InstaBox workspaces remain source/Git/docs/light-status only. Builds, syntax checks, fixtures, tests, benchmarks and raw artifact download/parsing stay Actions-only.

The existing three Claude background sessions remain on Windows with the user's Claude Pro usage; they are not copied, restarted or relabelled as remote sessions. Their branch results will enter the InstaBox product worktree only after independent acceptance, with necessary new-source CI.

User also requested an online handshake every 28 minutes. Active heartbeat `instabox-28` checks this exact machine and executes a lightweight command; healthy checks stay quiet, connection failures notify. The original 30-minute auto-suspend setting is unchanged. Claude completion heartbeat `exreader-claude` now contains the InstaBox worktree paths and merge authorization.

C3 independent audit has actually passed: `40952229357`, job `123723041261`, producer `40950703390` / source `9bced259710edff4bb98c730121ca09295500d73`. Root rechecked exact original ZIP, archive closed membership, all 22 file records, 15 SDK licences, 2 product licences, repository SQLite text and installed APK receipt. Independent artifact `12930674525`, 1456 bytes, SHA256 `e80da6b8aa39992de58c62c20b38c025390629f7215a703c7a29f9dd9588cb5e`. Original installed-tree comparison passed in the producer; the trees were not separately retained. F12 and common-source acceptance remain false.

C1 producer `40951458995` / source `7dce4bd6090cb8e1c1fa54b2329583bc55c3e138` passed, awaiting root independent review. C2 is still working. Fixed catalog remains 95/108; no Claude code is merged into the common source yet.