# D02：自定义字体本机导入与管理

先读[共同约束](README.md)。固定起点a826a65c9c66e43620eff61b49cb79f941a3c953；唯一分支 **codex/dot-reader-font-library**。

## 目标

独立默认OFF静态包，接收宿主明确选中的TTF/OTF/TTC字体文件/有界读取源，复制至本机私有字体目录；复用冻结SDK公开font接口真正打开验证，并为宿主返回可用字体记录。不注册系统字体、不安装到系统目录、不改排版引擎/字体回退或reading默认配置，不实现第二个字体解析器。

## 必须行为

- 公共C ABI：导入、按稳定内容hash列举/查找、打开所选已验证字体、显式移除。先读真实公开头和已安装font消费者再定函数；多face集合按SDK公开能力支持，否则明确UNSUPPORTED，不能声称导入全部face。
- 原文件名只作受限UTF-8展示，不作磁盘路径；稳定内部名由hash生成。拒绝符号链接/目录联接及非普通文件，打开后再校验，限额复制并校验实际字节，拒绝长度小报/中途变化/截断。单字体默认16MiB、硬64MiB；目录默认64个/128MiB、硬256个/512MiB，64KiB以内复制缓冲。不得整文件堆复制后假称流式。
- 同内容导入明确created=0；新字体先验证，再同目录原子发布。取消/写满/坏字体/冲突不破坏上一有效字体；目录独占及跨进程策略明确。失败返回不半填输出。SDK字体句柄遵守真实owner/释放规则，删除不得使已借用句柄悬空；必要时返回BUSY而非偷偷释放宿主句柄。
- 仅维护独立版本化本机清单，原子写出；未知清单版本、损坏、丢失文件按实际分类，不自动删用户原件。不新增产品schema或同步字体二进制。

## 范围

apps/reader/font-library/**；tests/reader_font_library/**；.github/workflows/reader-font-library.yml；docs/READER-FONT-LIBRARY.md；docs/validation/reader-font-library.json。

Actions三桌面安装C/C++消费者：合法许可固定字体、真实SDK打开/字形/简单排版，坏字体/截断/边界/取消重试、Unicode路径、去重、重开、真实终止发布前后、目录锁及释放寿命。字体许可、输入hash、真实程序和安装包均登记。无手机或宿主字体选择UI授予。
