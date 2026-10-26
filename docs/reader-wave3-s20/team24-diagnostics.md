# Team24 交付诊断接线

保留原 `validation.json` 和其中所有历史失败。原受测源码为 `63d0c8d2f032f5c78c77c9f407b17185412e991f`，run `40248648454`，attempt `1`。Windows、Linux、macOS、iPhone 通过；Android、iPad 未通过。

原 iPad 失败为 `test01ImportDeduplicateAndErrors`，不是已通过的 `test13`。原 job `121335559096` 的失败时间为 `01:02:28.467692Z`。新轮次必须保留对应原始 `xcodebuild.log` 与 `.xcresult`，以实际首次断言解释原因。

`tools/reader_wave3_package/diagnostics.py` 提供四个纯函数：

- `xctest_log(text)` 返回完整终结事件列表、passed、failed、failed_cases、first_assertion 和 assertions。失败后的成功重试不会删除原失败；断言附原始行号和前后上下文。
- `android_cases(validation, expected_total=45)` 根据独立命名用例重新计数，核对原 summary、唯一用例 ID、固定总数，并保留首个失败和 detail。instrumentation 进程退出 0 不构成用例通过。
- `candidate_identity(manifest, unpack, report, *, source_sha, run_id, attempt, sdk_version)` 返回身份问题列表。三个记录必须同源码、同 SDK 版本、同目标、同 run/attempt；校验原 ZIP 的名字/大小/摘要与实际程序摘要分别一致。它不取代 ZIP 字节校验和平台业务验收。
- `matrix_markdown(index)` 始终显示六目标，列出 ZIP 与程序摘要及未通过原因。输入是现有 summary 输出，缺失目标显示未通过。

父代理负责接入现有 `xctest.py`、`report.py`、`summary.py`，并在 workflow 的轻量检查中运行 `python tests/reader_wave3_s20/test_diagnostics.py`。这项协议检查只在 GitHub Actions 执行；不能替代六目标的真实启动与业务 GUI 验收。

新完整轮次单列 source/run/attempt，不拼接旧源码通过结果。SDK 的基础来源与 extra prefix 来源由构建阶段记录，不能仅凭版本号推断二进制来源。真机和读屏尚未测试。
