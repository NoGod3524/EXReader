# T01：Windows 云盘导入与书架批量整理实际界面

先读[共同约束](README.md)。独立从 `e4356a6e13223469fdf3b2f3d5171a6e99ab10a6` 创建 `codex/dot-windows-import-organize`；当前起点是共同宿主候选，不代表所有功能已验收。

## 固定依赖

普通merge这两份已复审交付，保留历史：
- J01云盘下载/侧载：`0d07d23bf53cd288de7a0af152d48553c18be241`，tested `80b743c6f51bee6d95e7cf116b4e65000a599063` / run40158826151，三桌面各47项及strict成功。
- J10批量整理：`757249aaed9a1dc6be981354f6af97e813233f04`，tested `fd2c88e3c5f0f0c7a7bd8698e7efb3825079bd41` / run40159996464，三桌面各21场景及strict成功。

只读公共头为 apps/reader/cloud-import/include/reader_cloud_import.h、apps/reader/bulk-organization/include/reader_bulk.h；阅读真实CMake/线程约定，不猜签名。J11新复审结果不构成本包依赖，本包不做冲突选择界面。

## 必须交付

在已有 Win32 正式 account host 上接真实功能，默认界面仍用现有Import/书架动作按需展开：
1. 使用已配置账号的真实WebDAV目录浏览、明确选书、网络worker下载私有staging，然后交现有单SDK owner导入；复用现有原件/产品映射和publication屏障。别在网络线程使用SDK句柄，不另开第二套书库。每个失败/取消/提交后清理都保留真实receipt；J01删除被拒时staged仍有所有权，不能丢失。
2. 书架真实多选，显式收藏/取消收藏、加入/移出已有子书架/标签/系列。调用J10，一项一事务、至多100；显示逐项committed/created/conflict和未执行项，允许取消与重开恢复。应用已成功但pending清理失败时仍显示已提交，并用原revision重试。
3. 同一SDK/产品owner和现有账号隔离；Modal、忙碌、切账号、最小化/关闭/重开不接受过期回调，不把未选中书修改。实际权限/不可用账号不降级明文。无新实体、schema或全局数据库。

## 独占路径

- `examples/reader.c`
- `apps/reader/windows-account/**`
- `apps/reader/desktop/windows_*`
- `apps/reader/desktop/windows*.*`
- `tests/reader_windows_import_organize/**`
- `.github/workflows/reader-windows-import-organize.yml`
- `docs/READER-WINDOWS-IMPORT-ORGANIZE.md`
- `docs/validation/reader-windows-import-organize.json`

其中合并进来的J01/J10模块保持上面固定树逐字相同。after-merge生产改动仅本表Windows宿主路径；不改desktop共享CMake、不改原Windows测试或其它工作流。新增代码尽量放Windows专属owner/.inc，由examples/reader.c最小接入。

## Actions验收

新专属workflow构建真实正式host，安装单份依赖，真实TLS目录/下载和九格式代表样本、明确选择/取消/401/失败原件清理、重复导入原件回读与映射；UIA真实多选和批量动作、并发冲突、取消、真实进程终止/原请求重投、未选中书不变。测试输入先固定，不能拿实现自报值作唯一预期。

同一最终二进制完整保留当前共同Windows原F1 264、F2 130、NavUI31、records32及原158/账号/书架等全部已有套件和原严格认证。可复制原workflow命令到新workflow并用新严格汇总绑定同一二进制；原测试文件逐字不改，遇缺陷交root最小复现。先不合入主线。
