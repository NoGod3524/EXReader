# 旧数据迁移独立复核

原始交付 `6515640`、原始云端成功与失败证据保持不变。修复分支为 `codex/wp12-migration-review`，尚未合入主线。

## 修复内容

- `verify` 比较包内标注指纹、账本保留记录指纹和归属、实际存储的文字及重排/固定页范围；不再把缺失映射当成已验证。
- 跨包部分迁移保留已有标注；已有标注的书未包含在本次包内时，也会验证其历史映射和实际存储。
- 验证音频书签的 ID、轨道、毫秒及标签。续播点登记迁移实际创建或保留的存在状态、轨道、毫秒与播放速率，包括零秒。已有续播点仍按原政策保留。
- 音频期望以可选 `resume_expected` 字段保存在账本；毫秒使用十进制字符串，避免 JSON 浮点精度损失。旧账本缺少该验证证据时，`verify` 明确拒绝，重新迁移可登记当前保留的续播状态。SDK ABI1/schema6 不变。
- 发布前复核目标和账本的存在状态与原有散列，处理末期取消。新目标及新账本使用原子无覆盖发布；文件系统不支持时明确失败。
- `verify`、`dump` 在打开 SDK 书库前检查目标，避免读命令创建不存在的库。
- 云端汇总核对源码、运行、attempt、工具/SDK/导出器/浏览器输入身份，以及完整具名检查、逐项计数和上游结果。手动运行同样执行汇总，测试结束后不自动改写受测分支。

## 验证口径

保留原 65 个命名场景及 135 项检查、真实 Chromium 导出和新进程迁移/重开链路。新增独立公开 API 状态编辑消费者、31 项迁移复核检查，以及汇总正反例。构建、测试、浏览器、语料与证据汇总全部在 GitHub Actions 执行；没有本地运行或工件下载。

原中间候选 `0a849b45aad3fe93db1fafe770aaa634be6e2b6c` 的两平台与汇总已成功，但它不含后续完整音频与汇总修复，不能替代最终候选。最终源码 `c2d23c29a3b2096c2236fdb414dcd1e66d3243b4` 的两平台及汇总已成功：每平台原 65 场景/135 检查、新增 31 项复核、17 项浏览器检查；汇总 29 项正反例通过。精确身份见 `docs/validation/wp12-migration-review.json`。这授予本包声明范围的独立验收，同源集成验收另行跟踪。

## 仍保持的声明范围

迁移工具不等于完整 WP12 高保真格式转换。未定位标注仍保存在账本；音频原件不进入书库，严格模式仍拒绝此类原件。超过 128 MiB 的原件、真实 Tauri 窗口、Firefox、WebKit、macOS 与真实用户库仍未验收。原限制及历史证据见 `docs/WP12-LEGACY-MIGRATION.md`。

实现与验证入口：`extras/migration/src/lm_main.c`、`extras/migration/src/lm_util.c`、`tests/migration/review_cases.py`、`tests/migration/review_edit.c`、`tests/migration/review_gate.py`、`tools/check_legacy_migration.py`、`.github/workflows/wp12-migration.yml`。
