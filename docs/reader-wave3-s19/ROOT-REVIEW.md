# S19 root review：明确修复与 Windows 单 provider 契约提案

本文件保留原移交检查点。Team24 后续接线及其待 Actions 验证状态见 [TEAM24-CORE.md](TEAM24-CORE.md)；原失败记录不变。

移交checkpoint：按root指令停止并写，后续由核心组合对话接手。除下述首阶段修复外，已保存但未验证的草稿包括：
Windows现有WIN32 target的static-only窄attach入口、反向多owner拒绝、实际安装SDK alias/SONAME与字节身份函数、
恰好三个同run平台工件规则，以及旧Windows shared-CLI报告不得授予真实GUI验收的阻断。
轻量协议测试及独立workflow尚未写入/启动；未执行任何新Actions，未推送本分支。新的runtime/图协议和真实Win32接入均待验证。
`run.py`白名单已预留`.github/workflows/reader-s19-root-review.yml`，但该workflow尚不存在；不要据此认为已运行验证。

状态：源码提案，未执行任何新构建、语法检查、测试或 Actions；原三轮及`accepted=false`不变。
本独立分支从`dab40686b1ca0d7ae0f5706f1dfe171c9300e9bd`创建，原S19工作区未改。
本阶段不启动S19第四完整轮，也不重跑C02性能；由root审查后另定一次有界验证。

## 已写入的最小明确修复

- `run.py`安装每个包时显式传`-DCMAKE_POSITION_INDEPENDENT_CODE=ON`，包括catalog及所有传递静态包。
  不改任何包实现、SDK源码、导出target或依赖；消除Linux已观测TLS静态对象不能进入DSO的构建前置问题。
- 负例拒绝文本与预期均用`' '.join(value.split())`归一空白，保留非零退出要求与原诊断词，避免CMake换行误拒绝。
- workflow在失败后也运行`--stage-only`并always上传。只复制已存在的日志、程序、CMakeCache/build.ninja、SDK DLL/DSO与Windows生成.def，
  同时保存真实driver outcome；部分工件的存在不表示验收通过。没有result.json时仍保留可诊断工件。

上述修改均未验证。本提案没有修改`tools/reader_host_feature_link.cmake`或五包target图。

## Windows：先证明原shared provider实际导出闭包

已知事实仅为原run `40246747578/1`的LNK2005/LNK1169；当前没有可下载的失败工件，不能认定具体缺失导出符号。
SDK`cmake/modules.cmake`的静态层明确传播`EXR_STATIC`，模块真实PUBLIC依赖仍指向这些组件；shared aggregate另有自己的import library。
Windows .def由`exr_layers`对应头生成。这里实际层是base/graphics/text/doc/formats/layout/render等，**并不是core层**；
`exr_font_count/open`直接声明于text.h。不能仅因core.h只include其他头，就推断上述符号漏导出。

批准一次有界验证时，应先保存并对照：

1. 该次实际生成`exreader.def`、安装的`exreader.dll`真实PE exports、五包及其传递包的`dumpbin /SYMBOLS`原始UNDEF外部SDK符号。
2. 逐项列出`UNDEF exr_* - PE exports`差集，处理实际COFF装饰与`__imp_`前缀，同时保留原始名字；不根据源码注释生成“观测结果”。
3. 若缺失符号导致静态archive成员被拉入，再用实际link map/原始LNK2005对象归属定位同一.o里哪些SDK符号发生重复。
   差集为空也必须保留该结果，继续查真实link line/成员选择，不能宣称DLL缺导出已证实。

任何需要修改冻结SDK export契约的修法都应另立候选、记录与`edddc463`的保护树差异并单独验收，不能藏在本helper里。
本提案不重贴SDK target、不删除模块传递依赖、不用`/FORCE:MULTIPLE`或相似选项掩盖重复实现。

## 真实GUI可用的static契约（尚未实现/验证）

原交接“SDK只在feature DLL内、宿主不再链接SDK”的static建议不适配现有GUI：
`apps/reader/windows-account/CMakeLists.txt`实际创建`EXReaderProduct WIN32 examples/reader.c`，
直接链接`EXReader::exr_core`，其`reader_catalog_sdk`还PUBLIC链接`EXReader::exr_library`；GUI源码自己大量调用公开SDK。
仅把S19命令行probe换成不调用SDK的加载器不能证明该GUI可消费这个DLL provider。

保持当前已安装static组件图不变的可行**源码契约**是：一个真实`EXReaderProduct.exe`成为唯一最终归属者，
以helper已有`SDK_LINK static`/`ROLE STANDALONE_EXECUTABLE`消费全部五模块、同一installed catalog和SDK；不加载feature DSO。
这符合现有GUI本来的直接SDK调用模型，且无需移除现有依赖或改造冻结SDK。它是待验证方案，未授予Windows通过。

批准后消费者工程应复用真实`apps/reader/windows-account`的CMake及`examples/reader.c`，补装其现有commands、desktop-metadata、
credentials、sideload依赖，保持同一安装prefix/版本；在真实WIN32 target上挂接closure，而非新建只有测试main的替代产品。
五包业务桥接可用同一`features.cpp`直接作为该GUI target的source，仍用真实公开API；必须让真实GUI进程实际发起五条路径，
并与GUI既有SDK调用共同完成身份验证。仅编译未引用archive或仅构建控制台程序不算完成。

必须产出的证据：真实EXReaderProduct的link map、PE import表、实际进程模块列表、SDK/五模块/store符号的真实成员归属，
以及GUI原有打开/绘制路径与五包真实业务结果。static模式应无exreader.dll导入/加载、无第二feature DSO；
一个最终EXE里的公共SDK/store符号应有唯一实现归属。不能继续套用旧shared模式“必须加载一个SDK DLL”的检查，也不能放弃单实现要求。
若root要求Windows继续采用shared SDK+feature DSO，则必须先完成前一节实际导出与UNDEF证明；本阶段不选择未经验证的fallback。

## 一次验证前另需处理的现有裁判阻塞

- workflow筛选恰好3个平台工件，verify.py却要求至少4个（包括它自己尚未上传的evidence）；即使三个平台结果全过也会拒绝。
  需由root明确改成真实输入集合，并保留三个必需平台与同次身份约束，不能简单绕过缺失输入。
- `run.py`早先用stem识别已加载SDK，最终`single_sdk_module`却用未版本化文件名精确count；ELF/Mach-O实际SONAME可能带版本。
  verify.py的dylib前缀也未覆盖`libexreader.1.dylib`。须按实际安装image/SONAME与加载路径统一身份规则，不能仅放宽成任意相似名称。

这些阻塞已记录，尚未修改裁判口径。保持旧结果accepted=false，等待root决定具体有界验证契约。
