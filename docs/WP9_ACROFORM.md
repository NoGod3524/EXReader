# WP9 AcroForm：字段快照与受限增量编辑

本分支提供 `include/exr/pdf_edit.h` 中的 `exr_pdf_form_read()`、
`exr_pdf_form_write()` 和配套释放/默认选项接口。WP9 仍为部分交付：
本页列出可运行的字段路径，以及尚未实现的外观和交互能力。

## 字段快照

`form_read` 返回独立拥有的 UTF-8 快照，使用 `exr_pdf_form_free(fields,count)`
释放。没有 AcroForm 时成功返回 NULL/0。有效字段名按祖先 `/T` 拼成限定名；
FT、Ff、V、DV、DA、Q、MaxLen、Opt 沿字段树继承，DA/Q 也可来自 AcroForm。
文本、复选框、单选组、选项列表/组合框具有类型、当前值与默认值；选择项
同时保存导出值和显示标签。签名、按钮和未知类型可枚举，但不能写入。

Widget 通过页面 Annots 映射到零起始页码，Rect 保留 PDF 原始坐标；
未出现在页面 Annots 中的 Widget 使用 SIZE_MAX。动作和 XFA 作为问题标志
返回。此接口不执行 A、AA、格式、计算、校验动作或 JavaScript。

字段树拒绝循环、共享子项、混合字段/Widget 子项、不一致 Parent、重复限定名、
非法类型、矩形和编码。默认值及硬上限为 4096 字段、16384 Widget、64 层树、
8 MiB 文本；调用方可设置更低上限。总树节点与修订对象各不超过 32768。

## 原子编辑和外观

`form_write` 接受按限定名定位的批量变更。输入字节始终只读，成功返回独立
输出并以 `exr_free()` 释放。输出保留原字节前缀，追加修订；失败和取消都
返回 NULL/0。零变更返回输入的独立副本。

已实现路径：

| 字段 | 值和 Widget 更新 | 校验 |
| --- | --- | --- |
| 单行文本 | V；每个 Widget 新建 Form 外观 | UTF-8、ReadOnly、Required、Unicode 标量 MaxLen、控制字符 |
| 复选框 | V、各 Widget AS、Off/导出名外观 | 导出名属于 Widget；Required 不允许 Off |
| 单选组 | V、每个 Widget AS、独立 Off/导出名外观 | 导出名属于组；NoToggleToOff 不允许全部关闭 |
| 列表/组合框 | V、I、显示标签外观 | 单/多选数量、选项成员、重复导出值与重复输入值 |

多选 V/I 按 Opt 顺序写入。每次变更同时更新全部关联 Widget。
保留原 NeedAppearances 请求，局部更新不能取消其他字段的外观重建。已有其他字段值和未替换的字典项继续保留。
AcroForm 本身可为直接或间接字典；要改动的字段和 Widget 必须有间接对象身份。

外观使用白底、黑框和黑色文字/勾号，按可用宽度缩小字体，支持 Q=0/1/2。
它重建值的可见结果，不保留原 DA 字体/字号/颜色、MK/BS 边框样式或原交互布局。
列表只绘制本次选中项标签；没有滚动条、选项菜单或焦点状态。

无宿主字体时，ASCII 32–126 使用 Helvetica。Unicode 路径使用调用方借用的
`exr_font` 指定字体面进行一次 LTR 塑形，再把轮廓写入外观；保存后重开无需
继续持有该字体。隐藏塑形字形不绘制；缺字、可见字形无轮廓以及需要双向布局
的文字返回 UNSUPPORTED。多字体回退、多脚本分 run、彩色/位图字形和可选中文本
字体嵌入未实现。宿主必须遵守 `exr_font` 的串行使用要求。

## 当前拒绝和未完成范围

写入拒绝多行、密码、文件选择、comb、rich text、可编辑组合框、多选组合框、
旋转 Widget、签名/按钮/未知字段、直接字段/Widget、动作/XFA、Catalog 权限约束。
加密写回、签名策略、动作执行、交互控件、原始样式保真及完整脚本布局均未验收。
本实现采用增量修订，历史值仍保留在原字节中；删除历史内容属于 WP10 重写路径。

## 独立文档语料（30 文件出口）

`tests/acroform_corpus/generate.py` 冻结 75 份原创 PDF，全部由该文件自行写出对象图，
不复制任何既有文件，也不下载外部出版物：35 份正例、29 份写入拒绝、3 份取消、
8 份树结构拒绝，覆盖 75 个类别（79 个字段、91 个 Widget、65705 字节）。每份文件
内容与 SHA 独立；云端连续生成两次逐字节比较一致，跨平台清单 SHA 完全相同。
预期值随语料写在同一张表里，并在任何实现读取文件之前写成 `corpus-spec.json`
与 `plan.tsv`，因此运行无法“发现自己”的结论。

`tests/test_pdf_form_corpus.c` 只做测量：枚举 → 编辑 → 写入 → 重开，并记录每个
注释的 AS/AP、未编辑注释的外观流散列、AcroForm 的 NeedAppearances、以及每个
已编辑 Widget 的实际墨迹。判定由 `tools/check_acroform_corpus.py` 依据冻结预期给出：
正例核对重开值、选项索引、按钮选中态、外观非空、未编辑字段值与外观保持；
拒绝例核对状态码、输出清空、源字节不变、重复调用与随后的零变更写入；
每份文件生成独立 JSON，汇总同时分开统计文件数、断言数和 CHECK 执行次数。

`tools/acroform_reference.py` 用三个外部实现交叉验证，避免只由同一实现自读自写：
qpdf 校验结构，pypdf 独立遍历字段树（继承、终止字段、Widget 数、on 状态、`/I`
与外观流文本），poppler 以 150 dpi 光栅化并按 Widget 内部矩形统计墨迹。
NeedAppearances 为 true 的两份文件由查看器重建外观，因此只做结构与字段交叉验证，
不作光栅断言，并在参考记录中写明原因。

`tests/consumer/form_consumer.c` 通过已安装的 `EXReader::exr_pdf_edit` 组件重跑
读取 → 编辑 → 重开路径，证明检查不是只存在于源码树内的专用命令。

## 可复现验收入口

全部执行放在 `.github/workflows/acroform.yml`。该工作流记录准确 HEAD，
在 Linux/Windows 构建真正的 C 实现，运行 `native-pdf-form`、原标注写入、
元数据写入、外观回归和 `native-pdf-form-corpus`，并单独运行 Linux ASan/UBSan
表单与语料测试及编译层检查；安装作业随后构建并运行已安装组件的表单消费者。
非 Linux 作业运行同一冻结语料检查，但外部参考工具只在 Linux 作业运行。

`tests/test_pdf_form.c` 在进程内生成原创 PDF，不依赖外部出版物：36 个字段、
39 个 Widget、嵌套继承、两页、单选导出名、选项对和多选。批改 34 个字段后
检查原字节、重开值、每个已改 Widget 外观流；另以独立文字区域验证 Unicode
不带宿主字体重开、清空后无文字墨迹。拒绝路径覆盖约束、树/编码错误、
资源上限、重复变更、缺字、空轮廓及开始/塑形中/输出完成时取消。
这是 1 个主表单定义、21 种 `source()` 输入定义（含该主表单）和 1 种深树定义，
独立审查后增加 radio 重复导出值的拒绝/同组选中回归，当前共 24 种进程内输入。
日志中的 9394 是 CHECK 宏执行次数，包含 PDF 构造器的格式/容量检查，
不代表 9394 个独立场景或文档；独立文档数由上面的 75 份语料另外统计。

受测源码 `a326fd38bbbb481da74657d682f649b1f45f7e2c` 的云端 run 为 `39833769030`：
corpus、Linux、Windows、sanitizer、evidence 五个作业全部 success。既有回归在两侧
各 4/4（表单 9394、元数据 1896、标注 492、外观 1629 次 CHECK），语料测试 1/1
记录 75 份文档、1798 次 CHECK；判定层 Linux 2032 条断言、Windows 与 sanitizer
各 1966 条断言，均为 75 通过、0 失败、0 跳过、0 缺失、0 重复内容。参考工具
qpdf 10.6.3、pypdf 6.21.2、poppler 22.02.0：输入 35 项字段树交叉验证、
输出 147 项检查（值、`/I`、on 状态、外观流文本、光栅墨迹），问题 0。
已安装组件消费者在 Linux 与 Windows 各覆盖 31 份、跳过 2 份（两份非 ASCII 值）、
失败 0。逐文件 JSON、manifest、参考报告和汇总由 evidence 作业提交到
`docs/validation/wp9-acroform-corpus/`；原始语料、编辑输出、测量日志、光栅页
和安装消费报告保留在该 run 的工件中。

精确源码 SHA、运行 ID、平台结果以同目录 `validation/wp9-acroform.json` 为准。
