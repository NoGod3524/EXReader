# CI hygiene (P)

P 基于 V 已合入的 ledger/base-20261103（34278023），不修改 F07 provider 或其工作流。V → P → C；R 的候选必须包含 P 及 F07 provider 的最终变更，不能沿用 V 的树。

## Four rules

- packaging：Apple host 之前必须安装同一 SDK 前缀的产品依赖。native.yml 的 macOS 与两种 iOS SDK 调用现有 build_apple_product.py。CI-DEPS-001 属打包遗漏。
- failfast：native 使用 bash .github/scripts/ci.sh {0}，开启 -Eeuo pipefail，错误打印期望/实际退出码/命令/候选脚本位置后立即退出。Windows SDK 示例保留 pwsh，开启 ErrorActionPreference=Stop 与 PSNativeCommandUseErrorActionPreference=true。显式 shell: bash 由 Actions 提供 -e -o pipefail，无须手写前奏；未指定 shell 的多命令块要求首行 set -euo pipefail，单条命令沿用退出码传播。静态检查不解析任意外部脚本；共享 shell 的真实退出行为另有运行测试。
- diagnostic：禁止无诊断的独立 test -n / [ -n ]。使用 ci_require_nonempty "$actual" "期望的值与来源" candidate/path ...，或者同行 || 失败分支打印 expected / actual / candidate。
- negative：用 ci_expect_failure command args ...；它显式 set +e、立即 rc=$?、set -e、检查 rc 非零，并原样打印被拒命令 stdout/stderr 与实际 rc。也接受内联同等结构；不能把错误丢入 /dev/null。

## Exact baseline, no directory waiver

PR 取实际 base SHA 作 diff 基点；手动调度取 origin/ledger/base-20261103，不能永久固定 V 的旧提交。被固化的是 JSON 条目，不是一个永远忽略后续基线增长的旧 diff 基点。

工具 tools/check_ci_hygiene.py 扫描所有 .github/workflows/*.yml / *.yaml。基线 tools/ci_hygiene_baseline.json 每条仅 file / line / pattern / line_sha256；pattern 是四种规则之一，哈希为该行去掉行结束符后的 UTF-8 SHA-256。全量扫描仍打印存量诊断。

- 文件/行消失、行哈希改变、规则不再匹配或条目重复：错误。修好后必须删除对应基线条目。
- git diff --no-renames -U0 BASE 的新增行不接受基线；未跟踪的新工作流全部视为新增行。新增或修改不按文件级豁免。
- 已登记行的行号变化也拒绝；不能靠重新登记新行号延续豁免。基线首次固化后只允许删除条目，不允许增补或改写。
- 不安全多命令步骤的新增正文行也受检，不能用未变化的首行基线覆盖它。
- 基线不支持目录或文件白名单。F07 文件没有例外；当前暂存线尚无 sdk-shared-sqlite-contract.yml，不能登记不存在的行。进入此线时新增违规会被拒绝，实际脚本由 F07 修复。

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

显式重生成命令：`python tools/check_ci_hygiene.py --emit-baseline`。基线 JSON 保留四字段逐行格式；旁边 ci_hygiene_baseline.meta.json 记录生成日期、源码 commit、生成器/基线 SHA-256 与 pattern 分布。CI 不自动生成或增补基线；此次重生成是 owner 明确批准的规则收窄，之后继续只减不增。

删除耦合：删除文件或删除步骤的同一 PR 必须删除对应基线条目，否则 CI 报“条目失效”（missing / no match / stale entry）；不能把失效条目留给后续 PR。
