# G13：GTK 键盘与无障碍审计

先读[共同约束](README.md)，接受其中全部不变项与云端执行限制。
固定实现起点：`f43baf9182d75907c0cb5d6f77048f27bca8c950`。新建独立工作树和分支 `codex/reader-a11y-gtk`。
类型：审计；优先级：P1；分发：DeepSeek Harness。

## 文件归属

- `tests/reader_a11y_gtk/**`
- `.github/workflows/reader-a11y-gtk.yml`
- `docs/READER-A11Y-GTK.md`
- `docs/validation/reader-a11y-gtk.json`

除此之外的目录只读。不要修改共享构建、已有工作流或本交接目录。

## 实现与边界

只新增测试，使用AT-SPI与真实键盘审计GTK书架、导入、整理、阅读、标注和账号界面的name/role/state、Tab顺序、焦点、弹窗恢复和状态通知。
基线支持什么就实际执行什么；不存在/不暴露的能力列明确缺口，不能自动修生产文件而与GTK接收owner冲突。
给出原生元素路径、复现、实际/预期、最小修复建议。AT-SPI审计不授予Orca/真人读屏通过。

## 云端出口

Linux Actions真实D-Bus/AT-SPI/Xvfb/窗口管理器，保存树/按键/截图。audit_completed与accessibility_accepted分离，有阻断问题保持拒绝。
所有发现可由固定source重放，失败不是“跳过成功”。
同一source/run/attempt逐项验收；参考通过记录不转移到本包源码。任何未覆盖能力继续保持未授予。

## 先读的实际代码

- `tests/linux_host/check_account_ui.py`
- `examples/linux/reader.c`
- `examples/linux/accounts_ui.inc`

## 交回

推送功能分支；完整受测SHA、最终纯文档HEAD/差异、run/attempt/job、具名结果、工件ID/字节/digest/有效期、原失败及剩余工作。不要替root合入。

