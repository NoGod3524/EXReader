# SDK 可靠性交付交接

## 2026-10-20 当前交付状态

第6节的工具、计量和证据拒绝条件已落地，字体依赖修正后的常规CI七作业通过。
整本验证工具提交的常规CI也已七作业全部通过，含Linux sanitizer；本批SDK与参考应用产物已独立归档。
新的96分片验收固定在修正提交上，仍未产生通过汇总；历史失败批次保持拒绝。
准确源码、CI状态和完整证据路径见 `docs/validation/2026-10-20-font-reliability.json`。

Windows/macOS/iPhone模拟器/iPad模拟器原生参考阅读应用的CI七作业全部通过；
Apple三类宿主各21项自动检查，Windows本地及CI各26项。
六平台SDK产物（iOS/iPadOS共享设备库）、依赖许可和设备IPA已下载并建立散列清单。
用户明确暂缓iPhone/iPad真机安装；完整生命周期、无障碍和其余应用功能仍按路线表验收。
记录见 `docs/validation/2026-10-20-native-hosts.json`。

已补整本遍历工具与逐文件隔离/证据驱动，GCC/MSVC专项各2/2通过。
真实公版EPUB已收齐500本，保留RDF、原书条款、散列与全部收集失败记录；整批验证已结束。
原始结果在`C:/Users/Oscar/exr-corpus-v1/epub-500-full/summary.json`：483本完成、11本超时、6本非预期，整批拒绝验收。
原批4进程、每本120秒墙钟；不要重跑覆盖。失败重放区分3本图像缓存预算、2本表格布局预算、1本内容区宽度错误。
122份外部PDF中49份完整完成，66份返回格式错误，7份返回不支持；未冻结逐文件能力预期，整批不验收。
10MiB多段单章完成首屏和采样翻页，50/100MiB单章仍受现有限制；WP6和首版完整交付均未完成。
范围和路径见 `docs/CORPUS_VALIDATION.md`、`docs/validation/2026-10-20-corpus-performance.json`。

WP6普通Latin表格宽度优化与兼容分类见 `docs/validation/2026-10-20-wp6-compatibility.json`。
SDK3.38.2、核心3.37.2、PDF3.38.1，ABI1/schema6；字体塑形/复杂内容继续使用原通用测量。
该优化不改变章内增量的未完成状态。WP7/WP8/WP12a使用各自HANDOFF文档中的独立分支和目录。

以下保留历史现场，版本、测试数及进度以各批次代码和独立验证JSON为准。

## 字体长测修正续批

长测39370107827已结束：parser/layout/render各24片通过，font24片失败，整体拒绝验收。
全部96份原始证据下载至`C:/Users/Oscar/exr-gcc/reliability-acceptance-39370107827`。
固定FreeType更新为VER-2-15-0；保留全部输入并增加`tests/fixtures/font-cff-regression.bin`回归。
新依赖下24份字体输入均正常结束，GCC/MSVC完整测试各150/150。
SDK/PDF补丁版本3.38.1、核心3.37.1，ABI1/schema6；版本声明更新后的准确CI结果继续补录。
记录见`docs/validation/2026-10-20-font-reliability.json`。原失败证据不得覆盖或计入新批时长。

## 2026-10-20续批进度

本轮继续第6节的计量、证据、CI与拒绝条件。下方原现场保留用于区分历史结果。

- CPU改为整数纳秒；schema2逐项校验报告、原始日志及附件。
- 构建清单封存四程序、运行库与配置；Linux验收检查ASan/UBSan导入符号，运行固定失败即停。
- 长测工作流增加归档重定位实跑、独立artifact目录、预期源码/清单/分片数/种子计划校验及上游失败拒绝。
- 最新GCC/MSVC专项各7/7；驱动31项、pipeline51项、合成计量127项。
- 四目标最新本地1秒CPU证据位于`C:/Users/Oscar/exr-gcc/reliability-20261020-r3-<target>/report.json`。
  旧目录及首次失败目录均保留。本轮没有修改引擎或公共接口，版本保持3.38.0。
- 验证及CI状态集中在`docs/validation/2026-10-20-reliability.json`。
  Windows短测、合成检查和工作流静态检查均不能代替Linux sanitizer或24CPU小时验收。
- 验证代码提交`8171284`：常规CI七作业全部成功，手动smoke六作业全部成功。
  两种工作流下载后的四目标证据均在本地严格重汇总通过。
  首次Linux合成超时测试隔离失败已修正，原始失败日志及上传附件分别保留。
- 长测`39370107827`已启动，源码固定为`8171284`，四目标各24分片、每片3600秒CPU。
  尚无长测通过汇总，不能记为24CPU小时验收完成。后续先检查此run，再决定是否需要重跑。
- 第6节的完整WP16发行条件及其他工作包继续按`docs/HANDOFF.md`跟踪。

日期：2026-10-20。下一批交付范围：完整 WP16；总项目范围仍为 WP1–WP16，含4a、12a，量化目标以 [HANDOFF.md](HANDOFF.md) 为准。

## 1. 接手现场

- 仓库：`C:/Users/Oscar/OneDrive/文档/ChatGPT/EXReader`。
- Windows ASCII入口：`C:/Users/Oscar/exr`。构建和驱动参数优先使用此入口。
- 分支：`codex/framework`。HEAD：`43daf5b58ea4edec07b8f14ffc6729763b6b3cf5`。本地HEAD与origin相差0/0。
- SDK3.38.0、核心3.37.0、PDF3.38.0、其余组件3.33.0；MIT、ABI1、schema6。
- 下述代码仍在工作区，尚未提交或推送。直接接着修改，不要重置、清理或重复应用补丁。
- 截止交接没有运行中的ctest、cmake、ninja或测试驱动进程；不要终止空闲MSBuild复用进程。
- 本批只扩展测试工具与计量，没有修改SDK公共接口或引擎源码，暂沿用3.38.0。

**必须保留**：未跟踪文件 `docs/validation/2026-10-19-shading-extent-ci.json`，SHA256：
`a955abda1e35fd456172b2e78e1d687799e4ab5f1f977dec0efd7684aae9fdc1`。
它属于上一批，不是本批验证结果；不要覆盖、删除或顺带提交。

先读本文，然后读 [FUZZING.md](FUZZING.md)、[HANDOFF.md](HANDOFF.md)、
[NATIVE_VALIDATION.md](NATIVE_VALIDATION.md)。
旧的 [TEST-DRIVER-HANDOFF.md](TEST-DRIVER-HANDOFF.md) 顶部已注明完成；下方保留的旧卡点是历史现场，不要重新按未完成任务执行。

## 2. 已提交基线，不要重做

CBZ截断压缩流不前进已修复，提交 `c8aa950`；固定样本为
`tests/fixtures/fuzz-cbz-truncated.bin`，908字节，SHA256：
`449011aa8cdd09984120b894e94309570113d7d6f7ccbbced27792824f9f48a7`。
有效CBZ成功，坏样本明确返回EXR_FORMAT。

上批GCC/MSVC各145/145；20万次、5种子、seed1完成，15919次成功解析。
[CI39363962576](https://github.com/NoGod3524/EXReader/actions/runs/39363962576)
在 `ff97fd1` 上7/7成功，后续HEAD只增加文档。准确记录见
[2026-10-19-fuzz-driver.json](validation/2026-10-19-fuzz-driver.json)。
该CI的失败附件步骤被跳过，没有实际验证上传。

## 3. 本批未提交改动

| 文件 | 内容 |
| --- | --- |
| `tests/fuzz_parse.c` | 原变异与保存循环增加编译期复用钩子；Windows GetProcessTimes / POSIX process clock；--cpu-seconds及实际完成次数 |
| `tests/fuzz_pipeline.c`（新增） | 字体、分页、绘制三个入口，复用同一变异/保存/重放循环；各自记录入口标签 |
| `tests/test_fuzz_driver.c` | 原28项增加CPU时钟检查，现在29项 |
| `tests/check_fuzz_pipelines.py`（新增） | 47项有效输入、确定性、记录、错误入口拒绝及CPU预算检查 |
| `tools/run_reliability_campaign.py`（新增） | 四目标定时运行、证据与散列、严格时长汇总；保留ASCII junction，不调用resolve展开中文路径 |
| `tests/check_reliability_campaign.py`（新增） | 27项纯合成汇总回归；合成数据不能当真实验收证据 |
| `CMakeLists.txt` | 三个新程序及五个新ctest；完整配置从145变成150项 |
| `.github/workflows/native.yml` | 增加pipeline契约与短测，失败时包含各入口样本和格式记录 |
| `.github/workflows/reliability.yml`（新增） | 手动长测草案：一份ASan/UBSan构建，四目标各24片，每片1CPU小时，最多8片并行，上传证据并严格汇总 |
| `docs/FUZZING.md` | 新入口/计时/界限/工作流；纠正默认seed与max-bytes口径 |

Windows路径修复已验证。原runner的resolve将ASCII入口展开成中文路径，窄字符文件读取失败；
现使用absolute保留junction。首次失败目录 `C:/Users/Oscar/exr-gcc/reliability-font-check` 保留，
后续成功目录为 `reliability-font-check-2`，不要覆盖首次失败证据。

## 4. 已实际验证，准确区分代码时点

- 接手时原驱动专项两套编译器各2/2成功。
- 新三个入口编译成功，专项曾各6/6成功；增加accounting后专项应为7项。
- GCC和MSVC全量各 **150/150通过**，耗时分别55.25秒、50.10秒。
  这两次全量中的accounting仍为25项；之后追加二进制/运行库一致性检查，
  最新27项已单独通过，尚未随最新脚本重新跑两套ctest专项。
- GCC短测：字体20000次、8种子、6444完成；排版2000次、123完成；绘制2000次、25完成。
- 四目标实际CPU短测均1.000000秒、exit0、passed=true：parser5532次/470完成，
  font8456/2699，layout5026/323，render3151/35。
- 成功短测报告在 `C:/Users/Oscar/exr-gcc/reliability-parser-check/report.json`、
  `reliability-font-check-2/report.json`、`reliability-layout-check/report.json`、
  `reliability-render-check/report.json`；旁有run.log和最后输入。
- 完整测试日志分别为 `C:/Users/Oscar/exr-gcc/Testing/Temporary/LastTest.log` 与
  `C:/Users/Oscar/exr-build/Testing/Temporary/LastTest.log`。
  GCC的LastTestsFailed.log仍有旧失败条目，不代表最近全量失败；以最近完整日志为准，不删除历史文件。
- 本批没有新的CI或本地sanitizer结果，没有完成任何目标24CPU小时。
- 本批尚未补NATIVE_VALIDATION、CHANGELOG或独立验证JSON。

## 5. 当前覆盖与界限

- font：TTF/OTF/TTC的face0；可变轴查询；混合文字LTR/RTL/竖排塑形，轮廓、位图和COLRv0层。
  尚不遍历TTC全部face，不构造轴极值实例，没有WOFF/COLRv1/SVG覆盖。
- layout：解析后分页，最多前4页，源范围与有限坐标检查。
- render：最多前4页，灰度和RGBA；重排192×256，PDF/CBZ按unit_scale缩至256像素内。
- 每次exercise最多4096次取消轮询；复杂有效文件可因限界返回取消，不代表完整绘制。
  `deep.fb2`已有深度拒绝；`pdf-blend/flat.pdf`可触发轮询上限。绘制正例使用
  `pdf-color/shading-axial.pdf`，已实际status0。
- 变异仍是字节级，非结构化裁剪；定时统计包含变异/保存的进程CPU开销。
- seed按 `seed | 1` 初始化；偶数和下一奇数重复，同目标分片应使用不同奇数。
- 汇总要求四目标齐全、同提交、干净源码、开启sanitizer、输入不变、同目标构建/语料一致、
  有效种子不重复、每片成功且CPU达标。仍需审查异常字段、构建证明及报告完整性。

## 6. 下一批完整目标与完成顺序

本批交付应完成WP16的可靠性工具和真实长测闭环，不在增加一个入口后停止。
同时逐项核对完整WP16发行条件；未满足的平台产物或消费验证继续保留为未完成，不能只凭长测宣布WP16交付。

1. 审查当前diff与新增文件，重点检查失败输出所有权、入口覆盖、CPU计量和汇总拒绝条件。
   审查手动工作流的运行库打包/RPATH、artifact目录合并、clean检查和超时。
   手动工作流尚未实际执行，不能先记为可用。
2. 重跑两套 `ctest -R native-fuzz`，确认最新27项accounting随专项成功；如改动引擎，再跑完整测试。
3. 以当前文件散列和准确代码时点补验证JSON、NATIVE_VALIDATION、CHANGELOG；
   SDK无功能变化时不逐项升版本。只提交本任务文件，不包含指定保留的未跟踪JSON。
4. 推送，等待常规CI全部7个作业成功；修复新暴露问题并保留原始失败证据。
   本地成功不能代替Linux ASan/UBSan结果。
5. 常规sanitizer短测通过后，运行手动长测。默认方案是4目标×24分片×1CPU小时，
   各目标至少86400秒实际进程CPU；缺失、失败、重复有效种子和不足时长不能记通过。
   记录run链接、源码SHA、程序/运行库/语料散列和全部报告；所有发现进入固定回归。
6. 汇总通过后保留完整证据。核对WP16的版本化文档/迁移实例、默认与裁剪安装符号消费、
   六平台产物、依赖许可与基准。移动交叉编译和设备运行分开记录。
7. 按 [HANDOFF.md](HANDOFF.md) 继续全部工作包，不把可靠性工具扩展算成其余功能完成。
   当前待办包括PDF剩余色彩与认证/绘制兼容、CSS/表格、章内增量、更多脚本、COLRv1/SVG、
   表单、redaction、OCR、转换、更多CBZ/流式媒体、应用/无障碍/TTS、OPDS/LCP。
   每项沿用路线表中的数量、性能、保真和设备验收条件；不能用接口存在代替行为验收。

## 7. 快速确认

```powershell
git -C C:/Users/Oscar/exr status --short

ctest --test-dir C:/Users/Oscar/exr-gcc --output-on-failure -R native-fuzz
ctest --test-dir C:/Users/Oscar/exr-build -C Release --output-on-failure -R native-fuzz

python -X utf8 C:/Users/Oscar/exr/tests/check_reliability_campaign.py
```

需要重建时使用 `cmake --build C:/Users/Oscar/exr-gcc --parallel 4` 或
`cmake --build C:/Users/Oscar/exr-build --config Release --parallel 4`。
依赖缓存为 `C:/Users/Oscar/exr-deps`，ICC-OFF构建为 `C:/Users/Oscar/exr-noicc`。
同一构建正在运行测试时不要改动源码、二进制或语料。

## 8. 约束

不改写历史，不覆盖既有未跟踪内容，使用UTF-8，保留MIT与第三方版权。
不增加贡献规范、额外署名、宣传或代理专用文件。
版本按更新规模批量分配：超大升第一段、中等升第二段、小修升第三段。
不能用交叉编译代替真机，不能用短测/墙钟/固定迭代数代替24CPU小时，不能扩大误差容差来通过比较。
