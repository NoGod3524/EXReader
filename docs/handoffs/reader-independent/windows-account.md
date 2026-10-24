# G01：Windows 账号、同步与收取界面

先读[共同约束](README.md)，接受其中全部不变项与云端执行限制。
固定实现起点：`f43baf9182d75907c0cb5d6f77048f27bca8c950`。新建独立工作树和分支 `codex/reader-windows-account`。
类型：功能；优先级：P0；分发：Claude Code。

## 文件归属

- `apps/reader/windows-account/**`
- `apps/reader/desktop/windows_accounts*.inc`
- `apps/reader/desktop/windows_catalog.inc`
- `apps/reader/desktop/windows_shelf.inc`
- `apps/reader/desktop/windows_metadata.inc`
- `apps/reader/desktop/windows_metadata_ui.inc`
- `examples/reader.c`
- `tests/reader_windows_account/**`
- `.github/workflows/reader-windows-account.yml`
- `docs/READER-WINDOWS-ACCOUNT.md`
- `docs/validation/reader-windows-account.json`

除此之外的目录只读。不要修改共享构建、已有工作流或本交接目录。

## 实现与边界

复用 reader_session_*、exr_credentials_*、exr_sideload_export_original、reader_revision_entities_page/selected/project 及 catalog 公共接口，把真实 Win32 产品宿主接上账号、手动同步、取消、重试和关闭。
账号设置放入次级入口，默认书架不增加常驻控制面板。安全存储不可用时明确“仅本次会话”；不写明文凭据。
全库本地原书按 catalog keyset 分页在 SDK owner 上导出，释放 source 后才启动网络；不遍历整个库到内存。接收先验证原件、投影 SAFE metadata、再以稳定私有文件导入并恢复映射，保留远端 title/author/favorite。
CONCURRENT、PENDING、墓碑均保持显式状态；当前阅读不因远端进度强制跳转。关闭等待 CLOSED 后 destroy，UI 不等待网络。
独立 apps/reader/windows-account/CMakeLists.txt 编译真实 examples/reader.c；不要改共享 apps/reader/desktop/CMakeLists.txt。Windows 专属 inc 由本包独占。

## 云端出口

Windows Actions 实际 Win32 UI、两独立产品/SDK库与原生 HTTPS；四格式原书和真实阅读 capture 往返、云端-only书下载打开、取消/重试、账号隔离、安全保存/会话凭据、活动阅读不被跳转、退出重开。
保留原 Windows UI158、产品10、worker5、书架UI13及本基线已支持的 metadata/整理出口；精确列出实际重跑项。三轮真实故障至少覆盖网络中断、导入后映射失败、扫描时关闭。
交付实际 EXE、链接图、UI操作与截图。新增UI必须由真实控件操作触发，不能只调用内部函数。
同一source/run/attempt逐项验收；参考通过记录不转移到本包源码。任何未覆盖能力继续保持未授予。

## 先读的实际代码

- `examples/reader.c`
- `apps/reader/desktop/windows_catalog.inc`
- `examples/linux/accounts.inc`
- `examples/linux/accounts_ui.inc`
- `docs/READER-GTK-ACCOUNT.md`

## 交回

推送功能分支；完整受测SHA、最终纯文档HEAD/差异、run/attempt/job、具名结果、工件ID/字节/digest/有效期、原失败及剩余工作。不要替root合入。

