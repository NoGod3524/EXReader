# Apple原完整记录套件：只读查询就绪准备候选

独立起点 `7c457fb68a24d917ac3bd60aa1f961b16fe9ae6b`，分支 `codex/reader-apple-records-ready`。尚未授予通过。

生产、SDK、原ReadingUITests七case、native19、两SDK构建、原collector和strict逐字不变。新工作流投影原records工作流，只增加实际分支/新守卫、设备环境准备、准备证据入原工件及严格复核。原SDK3.41/ON的有效配置明确绑定新分支，不伪造GITHUB_REF。原90秒断言、180/300秒用例预算不改。

原设备选择和erase完成后，在原xcodebuild前显式boot/bootstatus，再复用7c457fb6已完成的原Simulator窗口/bootstatus及最多180秒只读appearance查询就绪。准备不写appearance，不添加业务点击，不改或替换原七个用例。macOS记录无需模拟器准备。真实准备命令、退出码、耗时、stdout/stderr进入原UI工件，原严格裁判完成后再独立核对准备身份。

本轮目的为在系统实际就绪后完整重跑记录套件，判断原间歇tap失败是否仍发生；不将准备视作已确认的生产点击修复。失败保留完整xcresult/原日志/截图，不拼旧单平台结果，不重复刷短两case。raw3 iOS72、真机及完整产品保持未授。所有执行与工件下载/解析只在Actions，本地仅源码、文档与Git。
