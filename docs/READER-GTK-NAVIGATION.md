# GTK原生目录与按页入口

分支`codex/reader-gtk-navigation-ui`从Search最终证据HEAD
`9762a7dd4ede02b11339105ccd64b8d187f5d6bf`接续。原样引入已验F2源码
`cbd7832b914bddcf99e06a85962d301a00b47efa`的模块与原130项消费者；共享实现未改。
导航功能范围已在源码`f31858c6df4a4bf753a0caac67bf229b17b22ef1`的完整同源运行
[40128621078](https://github.com/NoGod3524/EXReader/actions/runs/40128621078)、attempt1、job`120975335174`通过。
原设置的两项整页配色检查仍严格失败，因此整轮`failure, accepted=false`。

| 范围 | 同源实测 |
| --- | --- |
| 新导航实际UI | 29/29 |
| 新导航owner后端 | 58项断言通过 |
| 安装后的F2公共消费者 | 130项通过 |
| 保留Search | 264项/34场景、后端296项、实际UI30/30 |
| 安装后的F3设置包 | 20组通过 |
| 原账号/接收 | 46项通过 |
| 原阅读/产品/固定页/书架/metadata/collections UI | 20+5+24+14+15+27=105项通过 |
| 原故障/回归 | 4项通过 |
| 定向真实AT-SPI | 10项通过 |
| 原设置UI | 全35项执行，33通过、2严格失败 |

两个失败原名为`light_foreground_and_background_change_page_pixels`与
`dark_theme_and_palette_change_page_pixels`，仍由下一次SDK画布能力候选处理。

可选`EXR_READER_GTK_NAVIGATION=ON`和安装前缀`READER_NAVIGATION_PREFIX`接入，默认关闭。
原“更多”末尾及Ctrl+Shift+T打开原生模态目录，每层只显示当前32行，可打开条目、进入子级、返回或继续分页。
作者标题按纯文本显示，不执行HTML。PDF/CBZ清楚显示“By-page entries · not an author outline”，不声称作者大纲。
重复spine列出候选、由用户明确选择；PART_ONLY必须再次明确确认才能尝试章节开头；外链不打开浏览器或网络。

所有F2快照、SDK对象、解析、关闭和可取消任务都在原SDK owner。来源key通过既有
`reader_catalog_sdk_original_identity`以64 KiB块重读真实原件，包含format、SHA-256及公开SDK版本。
模块在第一个新SDK对象解析后，第二个独立对象直接调用公开SDK的URI/CFI解析和page数组，
核对part/path/id/node或完整CFI点；不以重复调用同一个模块充当独立验证。
重排目标另在当前阅读对象严格resolve，仅FOUND且目标字节相等才走原帧接受/COMMIT路径。
有界EPUB先将公开pager的全部流式投影逐块与独立document比较，不拼第二份章节字符串，不猜两种偏移天然相同。
CFI raw UTF-16只有完整scalar且raw/规范化节点文本相同时才能映射；半surrogate、折叠空白和无法证明的点拒绝。
固定页无文本锚点时使用两个独立公开对象确认的page ID，再核对当前对象；不伪造文本FOUND。

浏览、分页、拒绝、取消和关闭不写原件、SDK notes/progress或产品revision/outbox；明确导航才允许位置提交。
关闭、后台、换书和退出使请求失效，并由同一owner执行强制关闭barrier；旧行和旧CFI不能重新生效。
不恢复未提交的目录对话框或CFI。冻结SDK、产品schema、F2、F3和Search公共模块保持原样。

F2复制快照完成后立即释放创建它的SDK输入；常驻快照没有SDK指针，解析时才创建两个独立输入。
行替换后恢复原生列表焦点；重复spine候选恢复焦点时仍保持未选择、Open禁用，必须明确选中。
探针等真实行分配和选中/Open就绪后只发一次打开快捷键。启动前确认Openbox就绪；
失败时保存原生window tree/PID/WM属性，原30秒映射及PID/窗口身份匹配保持严格。
大目录取消探针直接观察真实control阶段，不在打开后枚举或激活窗口消耗短任务窗口；
只发送一次零延时快捷键，保持原15秒观察预算，没有延迟生产代码或重放操作。

专项探针覆盖原F2夹具、45根条目32+13、Unicode层级、外部/越界/缺失目标、PART_ONLY、重复spine、完整CFI、
PDF/CBZ真实页入口，以及实际控制轮询中的取消/Escape/最小化/父关闭/进程重开。
同一源码已复跑Search264/34、Search后端296/UI30、F3 20、原46+105+4+AT-SPI10与设置35。
设置中的Light背景和Dark页色两个已知失败保持严格；缺口与下一次SDK候选方案见
[Search证据](READER-GTK-SEARCH.md)。整体`accepted=false`。

构建、语法检查、夹具、测试和工件解析仅在Actions；具体身份见[验证记录](validation/reader-gtk-navigation.json)。

## 工件与限制

同源工件`12574786910`，42,369,097字节，SHA-256
`9f25b18f3e11cdd73458db12163f2e1a4e6c774a662c044a6cf6197e75755a21`，
有效期`2027-01-22T20:10:46Z`；上传日志与API digest一致。
程序SHA-256为`1012d8fd3ed87ac9296e761d754a0304fbcdca0875e84dd58920c5d066c5a776`。
工件包含安装模块、唯一SDK/product provider记录、原始日志、逐项结果、真实帧截图、合成输入与保留回归。
授予范围是本次Linux/GTK的导航功能；性能、完整G13/Orca、整页主题及六平台互通继续单独验收。

## 保留的失败与诊断

| source / run | 原样事实 |
| --- | --- |
| `2799df58` / 40122987085 | 原`-Werror`拒绝四处misleading-indentation；语句分行后重跑，编译检查不变。 |
| `4ad9f45d` / 40123371736 | 导航/CFI/页入口已过；额外窗口枚举耗尽9000行工作窗口，观察时phase3/polls40，取消检查拒绝。 |
| `8bf2b68d` / 40124481444 | 完整轮次NCX行未selected/Open禁用，mnemonic未提交；保留套件通过、设置33/35。 |
| `28cc589a` / 40127001332 | 最初PID绑定的X11映射检查超时，未执行导航用例；失败后取消后续套件，run及always工件保留。 |

只读诊断`40126131632`从原failure-tree确认active modal、无焦点、行未选中与Open不敏感，
`diagnostic_only=true, accepted=false`。专项`40124093566`、`40126438508`与`40127877461`
分别在原source通过29项；最终授予使用上方`f31858c6`的完整同源结果。
