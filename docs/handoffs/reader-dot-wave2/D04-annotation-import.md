# D04：自有标注JSONL的严格导入

先读[共同约束](README.md)。固定起点a826a65c9c66e43620eff61b49cb79f941a3c953；唯一分支 **codex/dot-reader-annotation-import**。

## 目标

为现有EXReaderAnnotationExport提供真正可用的导入侧。先读apps/reader/annotation-export/include/reader_annotation_export.h、公开revision/reading-state头与原真实JSONL输出，使用该版本格式和原始wire。只接受自有结构化JSONL，不猜Markdown、别家格式或模糊位置，不改原导出模块。

## 必须行为

- 独立默认OFF静态C ABI包。显式书籍原始hash/format与宿主确认的目标一致，验证头/版本、每行字段/UTF-8、原wire长度/hash、唯一修订ID、尾部完整性和总数。输入先完整验证再首次提交；用同一打开源/有界私有spool避免两遍之间被替换。默认16MiB、硬64MiB文件；单wire沿用公开1MiB上限；不整份聚合进堆。
- 原wire和revision/parent身份逐字保留，使用公开revisions接收/应用接口；缺父/并发/墓碑/restore如实呈现，不自动选胜者，不新建同步实体，不手写SQL绕开公开校验。不重新capture或resolve到错误书，不写SDK notes/进度。
- 导入是明确逐项提交，不虚称全文件事务。每项返回新建/精确重复/冲突/缺父/拒绝与committed；稳定输入重投不重复history/outbox。取消不撤销已提交项，保留游标与真实结果；失败输出/重试和清理边界明确。
- 对同ID异wire、错书/错hash、未知版本、尾部缺失、重复JSON键、超限/坏转义/坏Unicode和截断必须在任何写入前拒绝。不对不安全头集进行自作主张的投影或时钟覆盖。
- 临时路径无符号链接逃逸；回调、线程owner和重入服从原revisions合同。完整包含的额外实体字段若公开接口不能无损导入，交具体缺口，accepted=false，不丢字段后声称无损。

## 范围

apps/reader/annotation-import/**；tests/reader_annotation_import/**；.github/workflows/reader-annotation-import.yml；docs/READER-ANNOTATION-IMPORT.md；docs/validation/reader-annotation-import.json。

Actions三桌面安装C/C++消费者：由未改G05真实导出生成合法输入，两端真实导出→导入→再导出核wire/头图/正文；并发/缺父补回/墓碑/精确重复/同ID异wire；取消、真实进程终止与重开重投；错误文件不改变既有库。绑定原模块树/消费者和全部具名正反例。没有宿主导入UI授予。
