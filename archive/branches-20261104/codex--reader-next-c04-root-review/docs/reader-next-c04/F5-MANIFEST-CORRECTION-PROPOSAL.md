# F5 新版清单修正提案（未实施）

原 F5 `278d63691a4c73e7aa932d71a40a5938c5427514` 的 Crowley 查询 `Policy and Procedure TTR` 是下载条目标题，不在实际正文中。保留旧清单、原预期、全部失败运行和 `accepted:false`。

## 证据

诊断 [40235597650](https://github.com/NoGod3524/EXReader/actions/runs/40235597650) 从固定原件（63797 B，SHA-256 `de6126e84aed9fa4204f4f7e84b1da6bedf4ef647479caa6a39befd40e9c5656`）经安装后的公开 SDK `exr_document_text` 导出 9215 B UTF-8 正文，SHA-256 `3335a98106684c882c5f5737db2e6d8bd13e7bb8631ecf9cbbde9ac9c18dadef`。

原查询精确查找、大小写折叠、再折叠空白后均不存在。正文首句为 `EH123 Rhetoric and Composition I`；`TTR` 在上课时间中，`Policy` 在考勤规定中，`Procedure` 不存在。不是通过换预期掩盖解析失败：同轮候选的两平台完整回归与原件解析结果独立保存在 [40234424624](https://github.com/NoGod3524/EXReader/actions/runs/40234424624)，原 F5 仍因查询和连带锚点失败。

## 单独版本的建议

新建独立、带新版本和新 SHA 的清单，仅修正 Crowley 的 `query` 为正文中连续的 `EH123 Rhetoric and Composition I`（当前公开导出 UTF-8 字节范围 `[0,32)`）。原件 URL、字节、SHA-256、作者、许可及所有操作预期不变；不将原 F5 改写成通过，不继承旧 run 的授予。

新版必须先在 Actions 独立核实固定原件与查询来源，再用该新清单对实际候选/批准 SDK 运行完整 Windows/Linux F5 操作，验证公开查找返回的实际范围、锚点 capture/resolve/reopen、原件回读及所有既有断言。预期 `find=found` 来自已导出的真实连续正文；锚点 `found` 仍是待验证要求，不将文本存在当成锚点已通过。

若只建立 C04 补充诊断，也应使用独立记录标为 supplemental，不能替代原 F5 `accepted:false`。SDK 候选是否接纳、何时建立新版清单，交由主线审查决定。
