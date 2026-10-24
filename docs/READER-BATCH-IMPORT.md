# 文件夹批量导入（EXReaderBatchImport 0.1.0）

## 固定起点与边界

- 固定起点：`c3511a011eefbf1fba1d20908f000cef22b1ced2`（`codex/reader-reading-v2` 上的同一交付起点）。
- 冻结 SDK：`9854061be331fe603a1822d9b2b36ee357154927`，SDK 3.40.0、ABI 1。
- 本包只新增 `apps/reader/batch-import/**`、`tests/reader_batch_import/**`、
  `.github/workflows/reader-batch-import.yml`、`docs/READER-BATCH-IMPORT.md` 与
  `docs/validation/reader-batch-import.json`。
- 不修改 SDK、共用宿主、产品 schema1、既有 wire、其他包和现有工作流；不写产品目录、
  修订、projection 或 outbox。

## 两阶段，无线程

1. **枚举**：`reader_batch_enumerate_open/next/close`。同步、增量；每次只保留当前目录、
   目录栈和一批候选，不缓存整棵目录树。可由普通 I/O worker 调用。
2. **导入**：`reader_batch_import`。1..100 项，必须在借入 `exr_library` 的 SDK owner
   上串行调用。没有后台线程、常驻监测或自动重试任务。

两阶段可独立调用：宿主可以先枚举并展示候选，再按自己的批次续批导入；模块不把
枚举结果偷偷转成导入。

## 枚举契约

- 递归必须显式设置 `recursive=1`；非递归只扫描根目录。
- 默认/硬上限：批 32/100；深度 8/16；目录 4096/10000；候选 4096/10000；
  路径 4096/32768 字节；枚举器保留内存 1 MiB/8 MiB。调用者只能调低。
- 只接受普通文件；符号链接、目录联接、FIFO、设备、目录和未知扩展名一律跳过。
  不跟随任何链接走出选定根。
- 扩展名只是候选过滤：TXT、HTML/HTM/XHTML、FB2、EPUB、DOCX、RTF、
  MOBI/PRC/AZW/AZW3/KF8、PDF、CBZ。真正的格式由 `EXReaderSideload` 验证。
- 只有正常扫完才返回 `complete=1`。达到任一边界、路径过长、目录不可读或条目被省略时
  返回 `truncated=1`；调用者不得把它报告为完整扫描。已经产出的候选仍然有效。
- 每个候选带绝对 `path`、`/` 分隔的相对路径、扩展名格式提示和仅作提示的
  `size_hint`；`size_hint` 不用于导入判断。

## 导入契约

每一项在导入时重新打开、重新校验，不信任枚举时的 stat：

1. 拒绝空路径、非 UTF-8、超出路径上限、非九格式和链接/非普通文件；
2. 以 no-follow 方式打开，确认为普通文件，取得当前大小和修改时间；
3. 按格式上限检查：重排 32 MiB、流式 EPUB/CBZ/PDF 128 MiB；
4. 以 64 KiB 缓冲复制到 `staging_dir` 中一个调用方私有的稳定临时文件；
   复制过程中检查取消、进度和源文件大小/修改时间变化；
5. 用这个稳定文件调用安装后的 `EXReaderSideload`，沿用它的精确去重、created 语义、
   PDF 稳定文件要求与协作式取消；
6. 无论成功失败都删除本次临时文件，返回每项状态。

因此 PDF 不会把用户目录中的可变路径交给 SDK；EPUB/CBZ 的流式上限和存储模式也由
现有 sideload 路径保持。

`committed=1` 只表示 SDK 返回成功。`created=1` 表示新 SDK 行；`created=0` 且状态
`DUPLICATE` 表示精确重复命中最旧的 SDK 行，旧书元数据、封面、进度和标注均不改。
模块不复制 import 实现，也不查询 SDK 私有 SQL 做去重。

## 错误与取消

- 单项失败（不存在、枚举后被删、变成链接、损坏、超限、格式不符）记录为 `FAILED`，
  `committed=0`，并继续后面的项。部分成功是可表达的。
- 取消只阻止尚未提交的项。已经提交的结果一定交回，且不会删除重复命中的旧书。
  取消发生在 staging 时该项为 `CANCELLED`、`committed=0`；取消发生在 SDK 调用期间而
  SDK 已提交时，结果仍为 `IMPORTED`/`DUPLICATE`。
- 批次返回 `READER_BATCH_CANCELLED` 表示后面的项被停止；已尝试项仍在结果数组里。
- 续批由宿主用下一批 1..100 项继续；模块不维护跨批隐藏状态。

## 回调与产品映射

`on_result` 在每项 SDK 导入返回之后、下一项开始之前同步调用；SDK 调用期间不会回调。
回调不得重入同一 library 或本模块。它拿到的是 SDK 结果，不是产品映射结果。产品目录
映射、revision、outbox 仍由 root 在 SDK 提交之后按既有流程完成；本模块不写产品 SQL，
也不把 SDK 提交宣称为产品映射提交。

## 验证

`tests/reader_batch_import` 在 Windows/Linux/macOS 安装后 C/C++ 消费者上生成：

- 多层目录、Unicode/空格/特殊字符路径、非书文件、目录伪装成 `.epub`；
- 九格式真实文件、`.azw3`（同一 MOBI 格式）、损坏文件、精确重复；
- 符号链接、Windows 目录联接、根外链接；
- 枚举后修改/删除/替换为链接；
- 深度、目录、候选、路径、保留内存、批大小、取消（提交后取消与 staging 取消）；
- 重开、重投、精确重复的 book_id/created、旧 metadata 保留、storage mode 保持；
- 通过公开 SDK 回读原件并与源文件 SHA-256 比对；
- 产品 SQL 表不存在，临时 staging 文件清理。

结果由 `docs/validation/reader-batch-import.json` 记录；云端 run/attempt、逐步检查、
工件 ID/字节/SHA-256/有效期与原始日志以同一 run 的工件为准。
系统选择器、宿主 UI、WebDAV 账号和新导入协议不在本包范围。

## 构建

```sh
cmake -S apps/reader/batch-import -B build/rb-adapter -G Ninja -DCMAKE_BUILD_TYPE=Release -DEXR_SDK=<sdk-stage> -DCMAKE_PREFIX_PATH="<prefix>;<sdk-stage>" -DCMAKE_INSTALL_PREFIX=<prefix>
cmake --build build/rb-adapter
cmake --install build/rb-adapter
```

公共头：`reader_batch_import.h`；CMake 目标：`EXReaderBatchImport::reader_batch_import`。
