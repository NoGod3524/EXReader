# D03：选中原书批量导出与分享准备

先读[共同约束](README.md)。固定起点a826a65c9c66e43620eff61b49cb79f941a3c953；唯一分支 **codex/dot-reader-original-export**。

## 目标与复用

可独立安装的静态C ABI模块，只从已有单SDK owner借用exr_library，通过安装后的公开原件/source接口把明确选中的书导出到用户给定目录；为系统分享或电脑拷贝准备真实文件。不是重新转换书籍，不复制SDK数据库，不读私有SQL或修改原书/notes/产品映射。

## 必须行为

- 每次最多100项，每项明确status/committed/created/format/原始hash/字节/输出路径；路径结果自有内存且文档说明释放。原件hash/格式必须来自公开读取并实际核验，不以本机book id作为导出后的跨设备身份。
- 文件名不信任书名或网络名称；提供稳定hash名及受限展示名。拒绝路径穿越、设备名、符号链接/目录联接别名；无覆盖发布。目标已存在仅在实际字节/hash相同且普通文件时记重复，否则CONFLICT，不能悄悄覆盖。
- 借用公开source，至多64KiB复制缓冲；继承实际原件上限，默认每书128MiB、每批512MiB，硬每批1GiB；限额先定，不改变SDK内32MiB/128MiB导入行为。打开源失效、共享owner拒绝、中途读失败都不发布前缀。
- 单项临时文件flush/fsync后原子无覆盖发布。取消停止未提交项；已发布结果保留，失败清理明确，不宣称全批事务。返回清理失败的真实所有权/receipt，不能丢路径。回调在SDK调用退出后，同owner拒绝重入/错线程。
- 可写明确版本的完成清单，但清单失败不能抹去已发布文件事实；完整清单只在真正完成后发布。模块不注册系统分享、不自动打开应用、不创建网络服务。

## 范围

apps/reader/original-export/**；tests/reader_original_export/**；.github/workflows/reader-original-export.yml；docs/READER-ORIGINAL-EXPORT.md；docs/validation/reader-original-export.json。

Actions三桌面安装C/C++消费者，九格式原件实际逐字回读、选中/未选中隔离、相同书/异内容碰撞、坏路径/Unicode、源失效、取消/写入故障、真实终止和重开重试；前后SDK原件、notes/进度与产品history/outbox不变。不得授予系统分享UI或六设备连线实测。
