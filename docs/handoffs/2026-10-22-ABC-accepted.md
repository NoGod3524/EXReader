# A/B/C 联合验收通过登记

2026-10-22。GitHub 只读核对完成：12 组运行、35 个上游作业均在 S 成功，
44 份上游工件同源、非空、未过期且具有有效 SHA-256 digest；严格汇总成功。

| 身份 | 固定值 |
| --- | --- |
| 共同源码 S | `686ce2fe6c3463ef1b917569677ee9933e22faa9` |
| SDK 基线 K2 | `d46ff370cb3c5ce9a0ceb4dc1f8b099209149280`，SDK 3.40.0 / ABI 1 |
| OPDS 祖先 H | `d10fa590609c820368266daac2b4b154e8e30a60` |
| 严格汇总 | run `39850404743`，protocol/baseline/summarize 3/3 success |
| 汇总执行源码 | `1c3e07247b09d14eb8fca6b9b53aa9b51e8993af`；日志受检 `source_sha` 明确为 S |
| 交付分支 HEAD | `1480b03d3f10ac750ff810e810eea3a1325b0ce0`，`codex/parallel-integration` |

| 组 | run | API attempt | 作业 | 工件 |
| --- | --- | ---: | ---: | ---: |
| native | 39844509983 | 1 | 7 | 19 |
| ocr | 39844519195 | 2 | 3 | 3 |
| corpus | 39844528742 | 1 | 1 | 1 |
| linux | 39844540267 | 1 | 1 | 1 |
| windows_evidence | 39844549354 | 1 | 1 | 1 |
| windows_worker | 39844559336 | 1 | 1 | 1 |
| migration | 39844568676 | 1 | 3 | 3 |
| opds | 39844589166 | 1 | 2 | 2 |
| apple | 39844598529 | 1 | 8 | 8 |
| android | 39844608350 | 1 | 1 | 1 |
| acroform | 39844617258 | 1 | 5 | 4 |
| spacing | 39844627315 | 1 | 2 | 0 |

汇总完成日志确认 `accepted=true`，两项 SDK 契约均为 K2，`pending_contracts=[]`。
汇总自身三份工件也均非空、未过期且 digest 有效，不计入上述 44 份上游工件。
K2 的 native/acroform/spacing 基线证据分别为 run `39837151097`、`39837165548`、`39837179303`，
已由云端严格基线检查接受。

Linux 记录存在一处口径差异：交付叙述及 JSON limits 写 attempt 2，
GitHub API `run_attempt` 与 JSON 的 runs.linux.attempt 均为 1；本表按 API 登记，保留原叙述不改写。
OCR 本轮 API attempt 2。其他旧失败与首次源码标签 `s1-2026-10-22-attempt` 保留在集成交付中。

完整记录位于固定交付提交：

- [联合验收 JSON](https://github.com/NoGod3524/EXReader/blob/1480b03d3f10ac750ff810e810eea3a1325b0ce0/docs/validation/2026-10-22-joint-acceptance.json)
- [SDK 基线](https://github.com/NoGod3524/EXReader/blob/1480b03d3f10ac750ff810e810eea3a1325b0ce0/docs/validation/sdk-baseline.json)
- [阶段一至四交付](https://github.com/NoGod3524/EXReader/blob/1480b03d3f10ac750ff810e810eea3a1325b0ce0/docs/PARALLEL-INTEGRATION.md)

只授予各包声明范围：`complete_product=false`、`wp16_accepted=false`、`wp16_cpu_credit_seconds=0`。
真实语料仍为 0/1710；Android 为 API34 x86_64 模拟器，真机及 VoiceOver/TalkBack 等出口另列。
R1–R6 的 A/B/C 等待条件已满足，本次只登记验收，不自动启动新工作包。
