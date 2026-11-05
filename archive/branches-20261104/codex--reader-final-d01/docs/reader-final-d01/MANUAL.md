# 人工验收：全部 pending，尚未执行

## 安全前置与失败留存

每平台使用**新测试系统账号或全新模拟器**，空书库、独立应用数据目录；不要借用私人云盘/生产书库。程序必须记录完整source、SDK、包/程序SHA-256、OS/设备/屏幕、开关、操作者、时间。没有与目标source一致的包则标blocked，不能换包补绿。测试用临时云端账号和专属 `D01-<日期>-<设备>` 根目录须事先获授权；本包没有创建账号、服务或凭据。

Actions原工件提供 `D01-clean.txt`、`D01-duplicate.txt`（相同字节）、`D01-corrupt.epub`（故意无效）。另使用仓库现有、已知能打开的干净EPUB/PDF/CBZ测试夹具，由其原Actions producer提供；不自行下载版权书或使用真实资料。新文件每个只有测试内容；记录原工件散列。测试结果不能以损坏文件拒绝替代正常格式的成功断言。

根据 `matrix.json` 的平台行查**准确UI路径与原标签**。Windows compact要启用相应构建开关；GTK为条件编译入口；Android为BuildConfig；Apple平台门控分别记录。入口缺失或按钮不可见：截屏并记录build开关，标missing/blocked，停止该项，不能改按别的入口代替。

每步失败立即保留：测试ID、环境/source/program hash、点击前后截图、原始日志（脱敏）、文件SHA/大小、可见状态、预期与实际、复现次数、恢复结果。先复制诊断再恢复，不删除失败证据；不要记录令牌、密码或私人路径。安全恢复通常为取消当前操作→正常关闭→重开独立测试库；若仍异常保留目录交owner，不手改数据库。

## 逐需求执行（每行适用于六个平台；未追踪入口先由owner补证）

|测试ID|前置状态和准确动作|可观察通过条件 / 失败恢复|
|---|---|---|
|M-R01|空库，从平台注册表R01进入系统选择器，选择D01-clean.txt，确认；点击新书名|内容可读、只有一本、原件在重开后可用；失败保留picker回调及日志，不改用拖放代替|
|M-R02|仅测试云盘Provider账号；从其系统选择器位置选同一干净文件。Windows“从云盘导入…”属于另一来源，须单列|实际Provider字节导入并可读；Provider不可用应可取消，不得将本地选择器成功算云盘通过|
|M-R03|专属WebDAV测试账号目录；按R03入口打开账号，同步一册测试书，第二个隔离客户端接收|原件SHA一致，书籍可打开；认证失败不泄露凭据，保留错误后退出会话|
|M-R04|真实电脑与目标设备、测试线缆；Android系统文件传输/Apple文件共享复制D01-clean.txt，再在应用选择该文件|真实线缆传输与实际宿主导入分别有证据；模拟器、下载或WebDAV不能替代；拔线前安全断开|
|M-R05|新测试目录包含两种正常格式及损坏文件；Linux Import sources ▾ > Import folder…；其他平台按已补入口|逐文件结果明确、失败不吞掉成功、不跨出测试目录；取消后重开不重复提交|
|M-R06|桌面已打开空测试书架；Linux拖放至书架滚动区，其他平台按确证目标|实际drop事件导入；系统选择器不替代；拒绝非法路径后仍可操作|
|M-R07|首开空库观察空态，完成R01后进入Windows视图>书架、GTK Shelf F2、Android书架、Apple书架|空态正确、新书可见可打开；重开保留，不以模块数据库查询替代UI|
|M-R08|GTK More>Collections…>Shelves；Android More>Organize；其他入口需补证；创建D01父架及子架，把测试书放入子架|父子关系重开保留，移动不会丢书；失败保留原结构不重写库|
|M-R09|同组织入口切Tags/分类，创建D01-tag并赋给测试书|筛选命中且去除标签不删除书；需独立于子书架测试|
|M-R10|同组织入口切Series，创建D01-series，两册设置顺序并重开|系列与顺序保持；不能以标签列表代替|
|M-R11|打开正常多页EPUB/PDF/CBZ；Windows阅读>下一页、GTK Next F4、Apple下一页；Android默认方向/点击模式下轻点阅读页右侧30%区域|实际页内容变化、前后导航、固定/重排各记；Android实际onTapZone→turnPage，字号变化不算翻页|
|M-R12|测试文本含D01 unique phrase；按R12搜索入口输入该词、选结果，再取消新搜索|结果对应实际正文、无错书跳转；取消不冻结，重新搜索可用|
|M-R13|有目录EPUB按R13目录入口，点第2章；PDF/CBZ按页入口独立记录|章节/页确实对应，缺失目录有明确状态；不能把页入口等同章节目录|
|M-R14|读至非首页，正常返回书架并关闭，重开同书；再从远端发送不同进度|本地进度保留；远端不得强制跳当前阅读位置；失败保留原锚点和resolve结果|
|M-R15|按R15阅读记录入口添加测试书签；翻页，打开该记录；重开再定位|FOUND才跳转，歧义/缺失保留原记录；无入口先blocked，不用数据库插入代替|
|M-R16|按R16选文/标注入口，写D01-note，编辑再删此测试标注|对应原文且重开编辑有效；只删除测试标注，失败不清空全部笔记|
|M-R17|按R17设置入口改变字号/主题后关闭重开，进入设置改值再取消|提交值保留、取消值不落盘；Apple A+只证明字号子项，完整面板另补入口|
|M-R18|已下载并打开测试书；断开测试设备网络，完全退出应用后重开书并翻页|原件离线可读，无账号阻塞；云端未下载书应提示而非误删；恢复网络仅影响测试设备|
|M-R19|两个隔离客户端先同步同书；同时离线编辑同一字段/笔记不同内容，再分别上线|保留多头冲突、提示明确，不按设备时间静默覆盖；无实际冲突UI入口则blocked并留两端原修订|
|M-R20|一次正常重开；一次导入进行中对测试进程终止，再重开|完整提交可见、未提交清理或明确重试；不误删旧书；终止前记录真实PID/阶段，不能用旋转代替kill|
|M-R21|先在系统picker点取消；再对足够大的干净测试文件在复制阶段点Windows取消当前任务、Android Cancel import、Apple取消；GTK先补真实取消入口|原书架不变且无悬挂busy；若已经提交必须明确反馈，取消不能删去重复命中的旧书|
|M-R22|导入D01-clean.txt后导入D01-duplicate.txt；再导入D01-corrupt.epub|重复不会新增书/删除旧书；损坏文件错误明确且旧书仍可读；保留原字节、错误日志|
|M-R23|测试账号先有效后由管理员撤销测试权限或在测试UI输入故意错误的临时凭据，点击同步|错误可见、凭据不入日志，离线旧书仍可读，可取消/重试；不得动私人账号|
|M-R24|记录测试资料清单；找到“仅移除本机下载”入口，仅移除测试书本机副本，再按同原件重新导入；最后注销测试会话|远端与metadata不被删，重新导入映射正确。全局删除与本机移除分开。测试环境交owner清理；不得删除真实书库或远端历史|

## 范围结论

一行运行通过只授予该source、程序、平台和案例。一次成功不填补其他平台；功能计数不换算“完整产品百分比”。首次使用、取消、重复/损坏、账号故障、离线、冲突、重开、定位与清理均须独立原始证据。真机、TalkBack/VoiceOver/NVDA实际朗读、USB、性能预算本包全部pending。

## 精确平台/配置勘误（优先于上方概述）

- Windows表中所有compact菜单路径：`apps/reader/windows-account`目标需 `EXR_READER_WINDOWS_COMPACT=ON`（默认OFF）；R12 SEARCH、R13 NAVIGATION、R15 RECORDS分别显式ON。账号来自该target编译定义。未开启时不是产品缺陷，也不能说入口已暴露。第三方Provider R02没有精确入口，不使用WebDAV云盘对话框代替。
- Linux产品宿主需 `EXR_READER_BUILD_GTK=ON`（默认OFF）。Import file/folder下拉需GTK_BATCH_IMPORT=ON；拖放需GTK_DROP_IMPORT=ON；账号、搜索、目录、记录、设置分别需GTK_ACCOUNT/SEARCH/NAVIGATION/READING_RECORDS/PREFERENCES=ON。组织入口还需READER_METADATA_PREFIX，GTK Collections面板选Shelves/Tags/Series。完整构建由owner提供，测试者不猜默认可见性。
- Android R11准确操作：打开多页测试书，默认 `turnDirection=1, turnInput=1`，取消选文后轻点阅读页右侧30%区域；`ReaderView`在ACTION_UP调用listener.onTapZone(1)，MainActivity调用turnPage(1)。字号键不是翻页证据。若改过输入/方向设置先恢复默认，或记录实际设置另测。R12/13/15/17的exrSearch/exrNavigation/exrReading/exrPreferences Gradle属性分别必须等于true；同步需exrSync=true。
- macOS：`compactLibrary=false`，书架点“打开文件…”；iPhone/iPad常规竖屏同“打开文件…”；iPhone/iPad横屏compact或辅助字号模式点顶部“打开文件”图标。阅读记录在阅读页ellipsis菜单 > 阅读记录，非工具栏直接按钮。分别记录平台和布局，不用一台设备结果填另两平台。
- Apple R17 A+只覆盖字号子项，不代表完整设置；各平台完整主题/取消语义必须另外找到精确入口才测。

## 补查得到的可执行子路线

- Windows R08/R09/R10：书库 > 批量整理…，Ctrl/Shift选择测试书，“明确动作”选加入子书架/加入标签/加入系列，选**现有**分组，应用到选中书籍。这不提供新建分组或系列排序证据；不得要求测试者凭该菜单完成不存在于已定位路径的新建动作。
- Windows R14：阅读 > 书签与阅读记录… > 保存位置；R17：设置 > 阅读设置… / Ctrl+,（WINDOWS_PREFERENCES=ON）。R19选冲突记录后恢复，先保留原版本；账号失败在同步账号面板看错误后重试。
- GTK R14：Reading records… > Save progress；R19：Account / Sync同步后的Version conflict列表；R21系统picker用Cancel，工作中用Escape（设置提交期间不强退）。
- Android R02：Import打开DocumentsUI后选择已安装测试Provider；没有Provider标外部环境blocked。R14：阅读记录 > 保存进度；R19：More > 同步 > 云盘书目点冲突书，会明确提示需要先解决冲突或恢复，这是拒绝不安全接收，不是完整冲突解决器。
- Apple R03/R23：顶栏本地书库/云盘书库 > 账号选择器 > 连接/更新授权；R14：阅读ellipsis > 阅读记录 > 保存阅读进度；R19同面板保留版本 > 明确恢复。
- 四平台R18均是已有本地原件打开路径，R20是正常重开/状态保存或Android pendingReady恢复路线。它们是隐式宿主动作，不新增“离线/恢复”按钮；完整断网、真实进程终止仍需原手工案例执行。
- R24共享reader_ld_remove模块未确立host入口；不要以删除书籍按钮代替。R04属于OS复制/真实线缆，不凭R01成功授予。
