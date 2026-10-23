# 阅读 SDK 发布准备

手动运行 `.github/workflows/reading-release-plan.yml`，输入完整 `source_sha` 与同源成功的 `accepted_run_id`。工作流只有读取权限，输出 `plan.json`、六个原始 tar.gz 与 `SHA256SUMS`，不创建标签或 Release。

准备工具要求目标源码已是远端默认分支祖先；`reading-required.yml` 的同次 17 个作业全部成功；严格摘要和 18 份上游工件的 ID、大小、digest 与当前云端一致，工件未过期。摘要签发者固定为 GitHub Actions。PR 临时合并源码、已有版本标签或 Release（包括 draft）均拒绝。

六包覆盖 reading-core / reading-library × Linux X64、Windows X64、macOS ARM64。只下载该轮原始工件，校验 candidate、内外 manifest、原 tar、逐文件大小及 SHA-256。宿主与架构核对 runner 字段，版本与 ABI 核对目标源码头文件。原 tar 不重建、不重新封装。

`tests/check_reading_release_plan.py` 使用合成正反例检查协议；合成材料不授予产品验收。真实发布准备仍需最终同源严格门禁通过且源码进入默认分支历史。
