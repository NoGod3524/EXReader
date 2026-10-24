# J04：Android 分享、打开与 SAF 文件入口

**可立即独立开工 · P0 · 用户手动分发**

先读[共同约束](README.md)，再执行本任务。仓库 `NoGod3524/EXReader`；固定起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`；唯一分支 `codex/reader-android-import-entry`。不要跟随主线或其它工作包HEAD；不要在现有宿主工作树切分支。

## 目标与复用

实现可由宿主接入的独立 Android library：接收系统打开/分享和 SAF 结果，稳定复制到私有文件，再把就绪请求交宿主 owner。

依赖只读：Android ContentResolver/SAF/ACTION_SEND/ACTION_VIEW；现有侧载公开契约。先阅读固定起点的公开头与已有安装消费者，确认真实签名和线程规则；不得按名字猜接口。其它J包、尚未合入的G包以及四套宿主当前改动都不是前置依赖。

## 必须交付的行为

支持 content URI、非 seekable stream、权限授予/撤销、取消和生命周期；64 KiB 有界复制，沿用 32/128 MiB 导入上限。不把 provider 的名字当路径，不解析书籍，不在后台线程直接触碰宿主 SDK。

公开接口要写清输入/输出、内存归属、线程/重入、错误、取消、提交边界和硬上限。实现可运行的最小原生组件与安装后接入范例，不只交设计或数据结构。

## 允许修改的全部路径

- `extras/android-import-entry/**`
- `tests/reader_android_import_entry/**`
- `.github/workflows/reader-android-import-entry.yml`
- `docs/READER-ANDROID-IMPORT-ENTRY.md`
- `docs/validation/reader-android-import-entry.json`

任务页、共同约束和其它路径由root维护，禁止修改。需要共享API或额外路径时，先交具体缺口，继续不依赖它的工作；不得擅自扩路径或依赖移动分支。

## Actions验收

API26 Debug/Release 编译；API34 模拟器真实自建 DocumentsProvider/分享 Intent，短读/未知长度/撤销授权/旋转/关闭/真实终止、重投去重、私有 staging 清理；最终用安装 SDK 导入并回读。

执行共同约束的源码/保护树/路径守卫、实际安装消费、具名正反例和严格同源工件汇总。不能以成功生成报告等同功能通过；模拟器/桌面/真机和实际音频/朗读等范围分别登记。

## 边界

不得改 examples/android、现有 Android owner 或 G 包；probe app 全在本包 tests 路径。

root负责当前宿主接线与最终共同源码复验。本包不因宿主未接线而免除上述模块实测。交回格式见[共同约束](README.md#交回)；完成后推自己的分支和真实证据，不停在请求push确认。

