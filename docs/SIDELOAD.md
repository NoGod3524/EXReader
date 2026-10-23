# 独立侧载导入模块

`extras/sideload`是可选静态C11模块，不进入默认SDK构建。
它只使用安装后的公开书库API，不改变SDK3.40.0／ABI1／schema7。
本地选择器、系统云盘提供器、WebDAV下载和电脑传入的文件可由宿主送入同一导入入口。
权限、文件复制、网络和UI由宿主管理。

## 安装消费

先安装`reading-library`，再独立配置本模块：

```text
cmake -S extras/sideload -B build/sideload -G Ninja -DCMAKE_BUILD_TYPE=Release -DEXR_SDK=<installed-sdk> -DCMAKE_INSTALL_PREFIX=<module-prefix>
cmake --build build/sideload
cmake --install build/sideload
```

下游将SDK和模块前缀加入`CMAKE_PREFIX_PATH`，使用
`find_package(EXReaderSideload CONFIG REQUIRED)`及`EXReaderSideload::exr_sideload`。
这些命令也由云端工作流执行；本项目开发约定的本地操作仅限源码、文档和Git。

```c
#include <exr_sideload.h>

exr_sideload_options options = {0};
exr_sideload_result imported = {0};
options.struct_size = sizeof(options);
imported.struct_size = sizeof(imported);
exr_status status = exr_sideload_import_file(library, EXR_EPUB,
    stable_private_path, title, &options, &imported, &error);
/* EXR_OK: imported.book_id is durable; created=0 preserves the existing book. */
```

## 输入、取消与所有权

路径和标题使用UTF-8，Windows文件路径转换为UTF-16。
`exr_sideload_import_source`借用不可变、可随机读取的source，只在同步调用期间使用，
不转移、不释放context。宿主负责串行使用书库及维持输入稳定。

EPUB/CBZ走公开source导入，PDF走公开file导入，统一上限128MiB；
TXT/HTML/FB2/DOCX/RTF/MOBI按64KiB读取到受限memory输入，上限32MiB。
options可以降低限额，不能提高这些上限。该上限是导入原件字节政策，不是解析峰值内存承诺。

source读取／分块复制可取消，SDK事务失败回滚。PDF和memory的SDK导入没有control参数，
模块在调用前检查取消；一旦提交，返回持久化的book_id／created，不事后伪报取消或自动删除。
PDF需要调用期间路径所指字节保持不变：SDK可能分别打开元数据和原件，单次stat或持有一个fd
不能提供该保证。宿主先复制到自己的稳定私有目录，再发起导入。

精确去重由SDK按格式与原字节完成，命中旧书会保留标题、阅读进度、标注及存储模式。
跨产品metadata库写入失败时，宿主按全局书籍身份重试映射，不能删除去重命中的旧SDK行。
EPUB有界导入后使用章内进度／标注接口；旧memory模式命中的书仍保留旧模式，须查询实际模式。

## 云端验收

`.github/workflows/reader-modules.yml`在Linux、Windows和macOS安装冻结SDK，
独立构建模块，再只用已安装模块和SDK构建公开消费者。
检查覆盖九格式、原件回读、去重保留、UTF-8路径、取消／IO回滚、限额、所有权和关库重开。
源码c2c75f99的[run39980923147](https://github.com/NoGod3524/EXReader/actions/runs/39980923147)
四作业同次通过：三个OS各完成模块消费者及安装后独立消费者，产品存储九组检查通过。
四份工件身份及旧失败见[模块验收记录](validation/reader-modules-c2c75f9.json)。
此范围不授予移动宿主、新产品UI或另一次PR总门禁验收。

首轮源码1ed8360的run39977249550保留为失败：三个OS均构建成功，
回滚用例的长ZIP注释输入在元数据阶段被拒绝，未进入待验证的分块写入；产品schema九组通过。
后继测试先证明较大CBZ可读，再注入首个64KiB之后的I/O／取消故障；原回滚及旧书保留断言保留。
该测试修订不改变SDK解析实现，也不授予长ZIP注释输入新的兼容性结论。
