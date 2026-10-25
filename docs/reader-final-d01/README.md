# D01 六平台首版需求追踪

**审查完成 ≠ 产品验收完成。** 本包不编译或启动宿主；真实设备、读屏、USB、云盘账号、性能和六平台同步全部未授予。当前状态见 [validation.json](validation.json)。

## 固定身份与可再生数据

- 入口源码固定 `0889f7d1e9a537c6c1b05456547e016b26e1cd85`，不是文档 HEAD。
- 指定 SDK `edddc463c06ed5731195cdb8f06b2df6dff7699e`（3.41.0 / ABI1 / core3.40.0）；本包不安装 SDK，因此该身份是目标约束，不是实际构建结论。
- [可审阅注册表](../../tests/reader_final_d01/catalog.py) 定义24条稳定需求及六平台入口。Actions 生成144行 `matrix.json`、可读 `matrix.md`、`findings.json` 和具名负例。不是空模板。
- `source_declared` 仅指已追踪源内处理入口；`implemented=null`、`exposed=false`，因为没有运行宿主。模块存在独立列 `module_present`。`evidenced` 表示当前固定目标的运行证据，本包全部 false。
- `trace_status=untraced` 是审查尚未追踪到精确入口，不是功能missing。Apple移动旧候选整轮失败仅留在其自身历史证据，不授予BASE blocked。所有行 `status=manual_pending`。
- 窗口/GTK/Android部分按钮本来为英文，注册表按真实标签记录，不伪造中文。一个组织面板内子书架/标签/系列分三条，入口共享不代表三条都通过。
- 原件落点由SDK owner管理；产品 `reader-catalog.db` 是独立目录/修订库。凭据属于平台安全存储或仅本次会话，不能写入产品同步载荷。记录中的数据 owner 为源码/文档归属，不是本包数据库检查结论。

## 证据与边界

六个不可变候选/历史 run 在注册表列出，Actions 保存其原始 run/jobs/artifacts API响应，检查受测 SHA、attempt、job及工件元数据。不同源码不拼接：Windows/GTK compact、Android raw3、Mac raw3、Android→Mac接收、Apple移动失败分别保留。

历史工件只核对元数据，不下载原候选大ZIP、不重新认证其宿主程序散列；`original_zip_reverified=false`。旧验收声明可只读参考，但本审查不重授旧产品能力。工件缺失、过期单独登记；不把 API 的 digest 当本包重算。

本包 producer 原 ZIP 在 strict job 下载，核对同 source/run/attempt、producer success、唯一名称、ID、非空字节数、到期、上传 digest 和 ZIP SHA-256；再逐成员核对 matrix/report 散列。程序身份是 Python审查器及 catalog 的实际散列，非 EXReader 二进制。无矩阵并发，两个job串行。

## 手工入口与阻断队列

[人工验收](MANUAL.md) 给出干净资料、各需求步骤、取消与恢复。没有入口的行先提交准确入口证据，再执行，不让测试者猜测。完整问题字段由 `findings.json` 生成。

1. root：固定最终共同产品源码并重跑六目标，不转授这些旧候选。
2. Windows/GTK owner：raw3共同接入和开关实际可达性；本包 compact源内声明不代表默认产品。
3. Apple owner：保留 `72c6bbdd... / 40203714083` 整轮失败，不能借iPad单叶通过。
4. 各宿主 owner：补齐未追踪的系统云盘、线缆、文件夹/拖放、组织、进度、离线、冲突、恢复、账号故障及本地移除入口。
5. QA：按144行独立记录实际手工结果、环境、二进制散列、失败原始材料；真机/读屏/性能另开授权范围。

## 已读与复用的基础

[产品目标](../READER-PRODUCT-PLAN.md)、[G1集成](../READER-G1-INTEGRATION.md)、[G01–G16输入身份](../../tests/reader_g1_integration/inputs.json)、[Android宿主导入/J04接线](../READER-ANDROID-HOST-IMPORT.md)、[Apple共同宿主与历史失败](../READER-APPLE-HOSTS-FINAL.md)、[整理模块](../READER-ORGANIZATION.md)、[仅移除本机下载](../READER-LOCAL-DOWNLOADS.md)、[既有Windows验收格式](../validation/reader-windows-compact.json)。复用 `tools/check_parallel_integration.py` 的官方API与ZIP下载认证入口；没有复制实现J/G/T产品功能。

## 再运行

在授权分支修改本包注册表/审查器并push；工作流只监听自身分支/路径。全部语法/测试/夹具生成仅在Actions。更新来源时必须同时更新目标约束/入口和原run身份，禁止只换成移动HEAD。最终文档封存使用 `[skip ci]`。

## 首轮结构绿灯后的语义纠正

首轮 `ee167af40c5bc43309e3bf6410b101e312ff2d38` / run `40215207810` 两job成功只证明当时的检查器接受数据。人工源码复查指出：Android翻页误连字号；Apple移动旧候选失败错误传播到BASE；条件源码声明误计实际exposed；144行矩阵误计144条入口已追踪。这些缺陷保留为首轮审查失败，不以CI绿灯覆盖。

修订：Android改为 `ReaderView.onTouchEvent → onTapZone → turnPage`，默认轻点右侧30%触区；Windows云盘导入不是第三方Provider，R02改为未追踪。每行独立 `source_declared`、`trace_status`、配置文件/原锚点/guards/defaults、`default_route_enabled`、`candidate_visibility`、`runtime_visibility`。未执行宿主，故 `implemented=null`、`exposed=false`、`evidenced=false`；全部状态manual_pending。旧Apple失败只保留在自身E-APPLE-FAILED历史记录，不传播到BASE。`traced`只计有精确入口者，`untraced`单列，`trace_complete=false`；`audit_completed`仅指结构与来源审查完成，不表示入口追踪完整或产品完成。

## 第二次源码研究：不把注册表遗漏当功能缺口

[research.py](../../tests/reader_final_d01/research.py) 补查进度、离线打开、重开/Ready恢复、账号失败、冲突历史、重复导入及组织子操作。精确定位Windows现有分组批量加入（不声称新建分组或系列排序）、四宿主本地打开/进度路径、Apple账号选择器与阅读记录版本，以及Android实际Provider选择入口。隐式生命周期也有准确source handler，不要求必须新增按钮。

剩余无host入口行逐项有 `research.classification/reason/references/source_searches`：外部OS线缆工作流；只有本机下载模块、未确立host调用；有文件夹/拖放模块而被审host未接对应路线；Apple共享catalog不等于组织编辑UI；Windows/GTK第三方Provider桥接未确立。搜索只证明所列source文件范围，不能称整个仓库不存在实现。每一行完成来源研究和状态归类，但仍不授予实际运行能力；精确入口完整度与144行研究覆盖分开。
