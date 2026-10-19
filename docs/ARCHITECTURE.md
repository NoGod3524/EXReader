# 分层整理：函数引用检查点

2026-10-19，0.19.0、ABI1、schema6。当前交付是**先清理内部函数依赖**；公开总头文件与CMake子库拆分尚未完成。

## 检查方法

`tools/check_layers.py`读取已编译的CMake目标文件，使用GNU/LLVM `nm`取得定义与未定义的`exr_*`符号，按`tools/layers.json`检查引用方向。一次引用以“消费者文件、提供者文件、符号”三元组计数，并非源代码调用次数。当前配置覆盖98个C源文件、1019条跨文件符号引用，**逆向引用0，例外清单为空**。

```sh
cmake --build build/native --parallel 4
python3 tools/check_layers.py build/native
```

Linux CI在构建后执行检查。新增未分类目标文件、缺失文件、循环层图或逆向引用会失败。`--prune`只删除已解决的例外，不能新增。负向验证将字体对象临时错误归到base层，检查器按预期报告新增逆向引用并返回失败，仓库配置保持不变。

检查结果限于当前编译配置的外部符号引用：不覆盖类型、宏、内联后消失的调用或其他配置下未启用的路径，不能代替内部头文件拆分。当前构建仍生成原有总库。

## 按实际职责修正后的层图

| 层 | 内容 | 可用的下层 |
| --- | --- | --- |
| base | 错误/取消、内存与源、UTF/URI/CSS扫描、通用位置/位图文件操作 | 无项目内上层 |
| graphics | vector/curves/dash/stroke/blend、canvas、affine_image、images、icc | base |
| text | 字体对象、字形/彩色字体、OpenType、双向、断词、可变轴 | base、graphics |
| doc | 文档树/构造、固定页provider、文本位置/锚点/CFI | text及其下层 |
| formats | 文本格式、EPUB资源/包、CBZ、XMP读取、导航/导出 | doc及其下层 |
| pdf | PDF解析、绘制回调、认证与编辑；当前含固定格式打开分发 | formats及其下层 |
| layout | 样式、行/表格/浮动/分页、书内字体装载、ruby、publication | formats、pdf及其下层 |
| render | 依赖字体和布局结果的页面栅格适配 | layout及其下层 |
| audio | 编解码/容器/时间线/播放/输出、WSOLA stretch | base |
| library | 书库、标注存储 | render、audio及其下层 |
| textindex | 书库文本索引 | library及其下层 |

`canvas`等不读取EPUB布局，是字体位图、PDF和CBZ共用的图形原语，因此放在text/doc下方的graphics层。`ruby.c`处理行盒和页面布局；`stretch.c`处理音频变速。`navigation.c`读取出版物结构而不做页面布局；`xmp_write.c`操作PDF对象，归pdf。

当前PDF固定页打开入口还分发CBZ并读取XMP，因此声明pdf→formats。以后拆窄PDF静态目标时，可将这段格式分发留在总库；不能用循环链接替代职责拆分。

## 已完成迁移与验证

| 步骤 | 结果 | 逆向引用数 |
| --- | --- | ---: |
| 原始建议图应用于实际构建 | 建立可复现基线 | 90 |
| 通用释放 | `exr_free`从library移到memory；metadata释放脱离fixed | 85 |
| 字体生命周期 | 创建/释放/引用/尺寸/度量/kerning从layout移到fonts | 68 |
| 文档分发 | 格式打开移到formats；模型释放/查询移到document；core保留基础设施 | 65 |
| 公共词法/路径和资源 | URI/CSS扫描下移，书内字体资源装载上移；模型/布局内存查询回到各自所有者 | 62 |
| 职责归类复核 | 建立共享graphics，修正ruby/stretch/navigation/XMP归属与有向关系 | 1 |
| 包视图接入 | CFI经document的`load_package`回调请求包视图；EPUB生产者设置/继承回调 | 0 |

各次代码迁移后的GCC完整回归均为131/131。最后一批为41.17秒；版本、公开函数签名、公开结构体大小和所有权约定保持不变。重新归类并非代码修复，表中单独列出，不将其冒充删除了61条错误调用。

准确代码提交`55089af`的CI7/7通过：三桌面各131/131，sanitizer128/128，Android与Apple移动库构建、20万次fuzz均通过。原始结果见 [验证记录](validation/2026-10-19-ci.json)。公开导出304个符号与基线相同。内部类型/公开头及CMake子库尚未拆分。

## 后续步骤

1. 拆内部头文件：先把base、graphics、font对象和document结构从公共内部头中分离，记录类型及include边；基础模块的独立编译不能依赖布局私有结构。
2. 拆公开`exr/*.h`，保留`exreader.h`作为总入口；每个头独立以C/C++编译，并验证旧入口符号、大小、偏移和callback前缀。
3. 最后拆CMake目标，显式声明依赖并正确保留总库导出；可选audio/library/textindex关闭时保留已声明的ABI策略。静态归档本身不验证所有引用方向，继续使用符号检查。
4. 对默认/裁剪组合做独立构建、安装消费及六平台验证；当前函数层检查点尚未宣称完成这些拆库验收。
