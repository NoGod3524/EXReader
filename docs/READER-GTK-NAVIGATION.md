# GTK原生目录与按页入口

分支`codex/reader-gtk-navigation-ui`从Search最终证据HEAD
`9762a7dd4ede02b11339105ccd64b8d187f5d6bf`接续。原样引入已验F2源码
`cbd7832b914bddcf99e06a85962d301a00b47efa`的模块与原130项消费者；共享实现未改。
源码`8bf2b68dba205a63d7cdae78b2dd0f139c04ffb4`的专项
[40124093566](https://github.com/NoGod3524/EXReader/actions/runs/40124093566)已通过导航UI29/29、
新后端58，以及F2原130项、Search264/34和F3 20。
同源完整保留回归[40124481444](https://github.com/NoGod3524/EXReader/actions/runs/40124481444)正在执行。

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
大目录取消探针直接观察真实control阶段，不在打开后枚举或激活窗口消耗短任务窗口；
只发送一次零延时快捷键，保持原15秒观察预算，没有延迟生产代码或重放操作。

专项探针覆盖原F2夹具、45根条目32+13、Unicode层级、外部/越界/缺失目标、PART_ONLY、重复spine、完整CFI、
PDF/CBZ真实页入口，以及实际控制轮询中的取消/Escape/最小化/父关闭/进程重开。
稳定后同一源码复跑Search264/34、Search后端296/UI30、F3 20、原46+105+4+AT-SPI10与设置35。
设置中的Light背景和Dark页色两个已知失败保持严格；缺口与下一次SDK候选方案见
[Search证据](READER-GTK-SEARCH.md)。整体`accepted=false`。

构建、语法检查、夹具、测试和工件解析仅在Actions；具体身份见[验证记录](validation/reader-gtk-navigation.json)。

保留的失败：`2799df58`/run`40122987085`因四处misleading-indentation警告在原`-Werror`下编译拒绝；
仅将语句分行，编译检查保持不变。`4ad9f45d`/run`40123371736`已通过导航/CFI/页入口场景，
但取消探针额外的窗口枚举耗尽9000行快照工作窗口，观察时已是phase3/polls40；保留该轮失败，
移除额外窗口操作后以新source重新执行。另以第二对象的原生SDK解析替代重复F2调用，并补精确位置断言。
