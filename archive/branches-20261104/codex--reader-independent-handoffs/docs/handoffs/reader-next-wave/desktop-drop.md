# J03：桌面文件拖放与粘贴入口适配

**可立即独立开工 · P1 · 用户手动分发**

先读[共同约束](README.md)，再执行本任务。仓库 `NoGod3524/EXReader`；固定起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`；唯一分支 `codex/reader-desktop-drop`。不要跟随主线或其它工作包HEAD；不要在现有宿主工作树切分支。

## 目标与复用

新增独立的 Windows/Linux/macOS 原生文件输入适配，输出拥有独立寿命的、数量受限的本地文件请求，供宿主随后交侧载。

依赖只读：现有平台原生文件拖放接口；extras/sideload/include/exr_sideload.h 的输入契约。先阅读固定起点的公开头与已有安装消费者，确认真实签名和线程规则；不得按名字猜接口。其它J包、尚未合入的G包以及四套宿主当前改动都不是前置依赖。

## 必须交付的行为

Windows HDROP/原生剪贴板、GTK text/uri-list、Apple NSPasteboard 分别接入。严格处理 UTF-16/UTF-8、file URI、百分号和换行；目录显式标记，不静默递归；网络 URL 与虚拟文件返回明确状态。

公开接口要写清输入/输出、内存归属、线程/重入、错误、取消、提交边界和硬上限。实现可运行的最小原生组件与安装后接入范例，不只交设计或数据结构。

## 允许修改的全部路径

- `extras/desktop-drop/**`
- `tests/reader_desktop_drop/**`
- `.github/workflows/reader-desktop-drop.yml`
- `docs/READER-DESKTOP-DROP.md`
- `docs/validation/reader-desktop-drop.json`

任务页、共同约束和其它路径由root维护，禁止修改。需要共享API或额外路径时，先交具体缺口，继续不依赖它的工作；不得擅自扩路径或依赖移动分支。

## Actions验收

三个平台原生小型 probe 窗口真实拖放/剪贴板消费；Unicode、空列表、多文件、重复项、目录、坏 URI、远端 host、过长输入、控件销毁和数据对象释放后寿命；安装后消费者。

执行共同约束的源码/保护树/路径守卫、实际安装消费、具名正反例和严格同源工件汇总。不能以成功生成报告等同功能通过；模拟器/桌面/真机和实际音频/朗读等范围分别登记。

## 边界

不修改现有宿主窗口，不访问用户剪贴板或私人文件；全部输入在 Actions 自建 probe 中生成。

root负责当前宿主接线与最终共同源码复验。本包不因宿主未接线而免除上述模块实测。交回格式见[共同约束](README.md#交回)；完成后推自己的分支和真实证据，不停在请求push确认。

