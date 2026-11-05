# 维护者来源与验收边界

入口：[中文指南](guide.zh-CN.md)。机器来源表：[source-inventory.json](source-inventory.json)。结果：[validation.json](validation.json)。

## 固定身份

- 正文默认实现：`0889f7d1e9a537c6c1b05456547e016b26e1cd85`，不是文档分支 HEAD。
- 批准 SDK：`edddc463c06ed5731195cdb8f06b2df6dff7699e`，3.41.0 / ABI1 / core3.40.0；原 3.40 冻结源 `9854061be331fe603a1822d9b2b36ee357154927` 不改写。
- D07 实际程序：Python 文档检查器；目标 ubuntu-22.04 Actions。**没有编译/执行 EXReader、SDK 或任何原生安装包。** 报告中的源码文件散列不是产品二进制散列。
- 每个正文 `G01`–`G17` 标记对应来源表的一行；每行记录平台、formal/optional/compact、源码路径、具名文本证据、既有证据 scope、人工未验证项。Actions 用 `git show 固定SHA:路径` 核对，并存储完整文件 SHA-256、逐条 needle 与外链原始结果。
- 无截图；不复用过期/未认证图片，不使用生成式 UI。

## 操作与来源索引

所有正式路径均在固定实现源读取；下表只是方便阅读的索引，完整路径/检查在机器表。

| 指南标记 | 操作 | 主要实际入口 | 范围 |
| --- | --- | --- | --- |
| G01 | 安装获取 | Windows CMake、desktop CMake、ReaderApp、Android Gradle | 无已认证用户安装包 |
| G02 | 导入/打开/翻页/返回 | examples/reader.c、linux/reader.c、MainActivity、HostViews | 六平台源码静态核对 |
| G03 | 继续阅读 | windows_compact_ui.inc、HostViews | compact 明确区分 |
| G04 | 格式/上限 | batch-import README、Android HOST-IMPORT、reader.c | SDK范围不借给host |
| G05 | 批量/拖放/云盘/连线 | batch_import_ui、drop_import_ui、windows_import_organize_ui | 可选开关；无连线服务授予 |
| G06 | 取消/重复/失败 | 批量契约、Android接线、reader.c | 保留提交边界 |
| G07 | 搜索/排序 | 四平台书架实现 | 无统一排序菜单 |
| G08 | 分类/系列/恢复/多选 | collections_ui、OrganizationPanel、windows_import_organize_ui | 不把恢复分组当恢复原书 |
| G09 | 删除区别 | reader.c、linux/reader.c、windows_accounts_ui | GTK Delete 是删标注 |
| G10 | 搜索/目录/记录/设置 | 各宿主真实操作面板 | feature flags需实际构建确认 |
| G11 | 固定页/定位 | NavigationPanel、HostReadingRecordViews | 无OCR或自动大纲承诺 |
| G12 | 地址/绑定 | account-profiles契约、各宿主账号表单 | 不改用户数据 |
| G13 | 保存凭据/首次同步 | windows_accounts_ui、accounts_ui、SyncPanel、HostAccountViews | 安全存储可用性另验 |
| G14 | 离线/重连 | 四平台账号处理者 | 手动同步，不授后台服务 |
| G15 | 冲突/恢复版本 | 各同步面板、HostReadingRecordViews | 无通用自动合并 |
| G16 | 七类故障恢复 | HOST-IMPORT、reader.c、HostViews、windows_accounts_ui | 未做实际崩溃恢复 |
| G17 | 去敏报告 | account-profiles 非秘密字段契约 | 安全建议，不发私密信息 |

## 既有候选证据不是本文的新产品验收

以下表格转录本轮冻结交接，不在 D07 下载旧 ZIP，也不借用不同源的成功片段。外链响应仅验证地址可达，不能认证内容或功能。

| 候选 | 受测源 / 文档封存源 | 既有运行 | scope |
| --- | --- | --- | --- |
| Windows compact | eab342ef456be4a8a1811e5249e3c217d906ce8a / f355525b74ae261db536c56200e46643919ef323 | [40201283788](https://github.com/NoGod3524/EXReader/actions/runs/40201283788) | 候选界面，不授共同源码六平台 |
| GTK compact | 57203a52aee439be5194ee0a4b13563a975e8daf / 9fc407a5cce5a0bfe644a60bd8dc29f84dea6d0e | [40206458217](https://github.com/NoGod3524/EXReader/actions/runs/40206458217) | 独立候选 |
| Android raw3 | 4a04a9cc74dde67f755c87e87b278d63a254a3ac / caa84411ae79c866c28cf982243b6cb80b4bbe49 | [40207467982](https://github.com/NoGod3524/EXReader/actions/runs/40207467982) | 模拟器候选不等于真机 |
| Mac raw3 | 15dab6b2270dc296ed6239db67ced2e22d255e65 / 44eabdc86b3b84d986f81dbaf8cee92b1829cea8 | [40196978163](https://github.com/NoGod3524/EXReader/actions/runs/40196978163) | 独立候选 |
| Apple 移动 | 72c6bbdd14ebf3be453fa7f0da81119d52675eb5 | [40203714083](https://github.com/NoGod3524/EXReader/actions/runs/40203714083) | 整轮失败，iPad单叶过不授整轮 |
| Android旧导入接线 | a7b2cb391c24a8ca0db3ff1472e3bfed84248be6 | [40173100103](https://github.com/NoGod3524/EXReader/actions/runs/40173100103) | API34 x86_64，原文120项；非本轮重新运行 |

## 发现与 root 后续

1. `examples/windows/README.md` 描述目录内 reader.c，但 CMake 实际复用 `../reader.c`，且 README 部分还是 WP13 历史语境。本文以真实 CMake/处理者为准，未改 owner 文档。
2. GTK `Delete F10` 实际 dispatch `READER_NOTE_REMOVE`，不能翻译成“删除书籍”。
3. 界面中大量英文与编译开关仍存在；统一中文及发行配置需要 root 确认，D07 不生产产品修改。
4. Android 暂存模块128 MiB与宿主32 MiB不可混淆；最终 raw3 是否改变范围必须在统一源重新验收后更新指南。
5. 未认证六平台可安装发行物、签名、真实 WebDAV、USB、第三方云盘、读屏、真机和性能；无通用恢复原件/全库冲突自动处理入口。
6. Apple 移动候选整轮失败保持原结论；本指南源码步骤并非实际验收通过。
7. 本次自动检查只授予链接与来源完整性；中文语义为人工源码审读，不是机器证明所有行为正确。产品 accepted 始终 false。

## 复核方法

只在自有分支 Actions 执行 `tests/reader_final_d07/check_docs.py` 和 `authenticate.py`。首作业检查固定起点祖先、白名单路径/保护树、全部源文件、Markdown相对链接及中文锚点、HTTP外链和坏链接/缺来源负例。第二作业认证同 source/run/attempt 的首作业、工件ID/名称/大小/原ZIP SHA-256/有效期，再比对包内文档与检查器字节，并拒绝错源、缺项、重复、篡改。末尾 evidence 自身的 ZIP 身份在上传后由同 Actions 作业再读取认证并写日志，避免循环自包含伪证。
