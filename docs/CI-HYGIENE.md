# CI hygiene (P)

P 基于 V 已合入的 ledger/base-20261103（34278023），不修改 F07 provider 或其工作流。V → P → C；R 的候选必须包含 P 及 F07 provider 的最终变更，不能沿用 V 的树。

## Four rules

- packaging：Apple host 之前必须安装同一 SDK 前缀的产品依赖。native.yml 的 macOS 与两种 iOS SDK 调用现有 build_apple_product.py。CI-DEPS-001 属打包遗漏。
- failfast：native 使用 bash .github/scripts/ci.sh {0}，开启 -Eeuo pipefail，错误打印期望/实际退出码/命令/候选脚本位置后立即退出。Windows SDK 示例保留 pwsh，开启 ErrorActionPreference=Stop 与 PSNativeCommandUseErrorActionPreference=true。显式 shell: bash 由 Actions 提供 -e -o pipefail，无须手写前奏；未指定 shell 的多命令块要求首行 set -euo pipefail，单条命令沿用退出码传播。静态检查不解析任意外部脚本；共享 shell 的真实退出行为另有运行测试。
- diagnostic：禁止无诊断的独立 test -n / [ -n ]。使用 ci_require_nonempty "$actual" "期望的值与来源" candidate/path ...，或者同行 || 失败分支打印 expected / actual / candidate。
- negative：用 ci_expect_failure command args ...；它显式 set +e、立即 rc=$?、set -e、检查 rc 非零，并原样打印被拒命令 stdout/stderr 与实际 rc。也接受内联同等结构；不能把错误丢入 /dev/null。

## Exact baseline, no directory waiver

PR 取实际 base SHA 作 diff 基点；手动调度取 origin/ledger/base-20261103，不能永久固定 V 的旧提交。被固化的是 JSON 条目，不是一个永远忽略后续基线增长的旧 diff 基点。

工具 tools/check_ci_hygiene.py 扫描所有 .github/workflows/*.yml / *.yaml。债务身份为 **(file, content_sha256, occurrence)**：SHA-256 对整行 UTF-8 内容计算（不含换行符），occurrence 是该内容在同一文件全部行中的第 k 次出现，从 1 开始。行号仅用于即时诊断，不参与身份。

每个内容身份的 patterns 列表保存独立规则义务；同一行同时违反两条规则时合为一个身份、保留两个绑定，不能借一个规则的历史债务豁免另一个规则。

- 行挪动且内容/同内容出现序号不变：身份保留，不失效。
- 内容变更或新增重复项：新身份必须合规，不自动登记；与基线 source 比较内容出现集合，不把纯位置变化当新增。
- 文件/内容消失、某个规则已修复、身份重复或义务失效：报错，同一 PR 必须删除对应条目/规则绑定。
- 基线固化后只允许缩减身份或规则绑定，不允许新增豁免；没有目录级或文件级 waiver。
- 不安全多命令块中真正新增的内容也受检，不能用旧首行身份覆盖新增违规。
- `python tools/check_ci_hygiene.py --remap-baseline` 只映射已存在条目，不扫描追加新债；无法映射时逐条记录原因并停止写回。
- 本次原 533 条全部映射，成为 531 个内容身份、533 个规则绑定；两处同一行的 failfast/negative 合并，零无法映射。详情见 evidence/final-gate-probe-20261103/baseline-remap.json。

## Focused acceptance

native.yml 保留原 PR/push 触发语义；P 使用 [skip ci] 提交，避免触发完整 native 矩阵。只手动调度 scope=p-hygiene（四个 Ubuntu 规则 job）及 scope=p-apple（三个 Apple 产品安装 job，不渲染、不跑性能矩阵）。scope 默认 full，原日常矩阵保持原行为。

```sh
python tools/check_ci_hygiene.py --base BASE_SHA
python tests/check_ci_hygiene.py --rule diagnostic
# CI: fault=none is the positive control; one rule job for each negative.
gh workflow run native.yml --ref codex/ci-packaging-hygiene-20261103 -f scope=p-hygiene -f fault=none -f rule=all
```

fault 的四项 packaging/failfast/diagnostic/negative 只改内存中的 native.yml 副本一处，对应规则 job 直接返回 exit 1 并打印诊断，不写仓库、不改远端 ref。baseline-new / baseline-modified / baseline-stale 在独立临时 Git fixture 里各造一次新增违规、修改基线行、修复却未删条目，diagnostic job 返回真实校验 exit 1。临时路径在入库证据中替换为 <temporary>。

三种 Apple 产品安装为必要构建验证；不启动原 desktop/sanitizers/fuzz/android/apple-mobile 作业。不得为 P 运行完整 native 矩阵，也不执行 refreeze。

## Narrowed command rule and regeneration

显式 `shell: bash` 按 GitHub 的 bash -e -o pipefail 执行，单/多命令都不要求手写前奏。未指定 shell 的 Linux 默认是 bash -e，无 pipefail：仅多命令、管道、&&、分号、循环/条件要求首行 set -euo pipefail；单命令、单个 heredoc、反斜线续行和引号内 Python 内容不算多个 shell 命令。pwsh/powershell 不论单/多命令均要求 ErrorActionPreference=Stop 与 PSNativeCommandUseErrorActionPreference=true。continue-on-error、|| true、; : 始终拦截。

显式重生成命令：`python tools/check_ci_hygiene.py --emit-baseline`。基线 JSON 记录 file/content_sha256/occurrence/patterns；旁边 ci_hygiene_baseline.meta.json 记录生成日期、源码 commit、生成器/基线 SHA-256 与 pattern 分布。CI 不自动生成或增补基线；此次重生成是 owner 明确批准的规则收窄，之后继续只减不增。

删除耦合：删除文件或删除步骤的同一 PR 必须删除对应内容身份/规则绑定，否则 CI 报“条目失效”（missing / no match / stale entry）；不能把失效条目留给后续 PR。
