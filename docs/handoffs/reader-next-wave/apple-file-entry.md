# J05：Apple 文件选择、文件共享与安全作用域入口

**可立即独立开工 · P0 · 用户手动分发**

先读[共同约束](README.md)，再执行本任务。仓库 `NoGod3524/EXReader`；固定起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`；唯一分支 `codex/reader-apple-file-entry`。不要跟随主线或其它工作包HEAD；不要在现有宿主工作树切分支。

## 目标与复用

提供 macOS/iPhone/iPad 独立文件入口组件，接入用户选择文件及文件共享 Inbox；产出稳定私有文件请求供 SDK owner 导入。

依赖只读：Foundation file coordination/security-scoped URL；现有侧载公开契约。先阅读固定起点的公开头与已有安装消费者，确认真实签名和线程规则；不得按名字猜接口。其它J包、尚未合入的G包以及四套宿主当前改动都不是前置依赖。

## 必须交付的行为

成对管理 security scope、协调读取与资源释放；iCloud 未下载/读取失败明确上报；不强制主线程复制整书。保留精确原字节、Unicode 和取消/关闭语义，沿用导入限额。

公开接口要写清输入/输出、内存归属、线程/重入、错误、取消、提交边界和硬上限。实现可运行的最小原生组件与安装后接入范例，不只交设计或数据结构。

## 允许修改的全部路径

- `extras/apple-file-entry/**`
- `tests/reader_apple_file_entry/**`
- `.github/workflows/reader-apple-file-entry.yml`
- `docs/READER-APPLE-FILE-ENTRY.md`
- `docs/validation/reader-apple-file-entry.json`

任务页、共同约束和其它路径由root维护，禁止修改。需要共享API或额外路径时，先交具体缺口，继续不依赖它的工作；不得擅自扩路径或依赖移动分支。

## Actions验收

macOS 与 iPhone/iPad simulator 独立原生 probe；真实本地 URL、Inbox、多文件、只读/撤销/移动、部分复制、取消、重开、释放 scope 后 staging 仍稳定；公开 SDK 九格式回读。系统云账号及真机能力未实测则明确 pending。

执行共同约束的源码/保护树/路径守卫、实际安装消费、具名正反例和严格同源工件汇总。不能以成功生成报告等同功能通过；模拟器/桌面/真机和实际音频/朗读等范围分别登记。

## 边界

不写现有 Apple Host*.swift、工程或账号文件；不接触真实 iCloud 账号、不改签名发布设置。

root负责当前宿主接线与最终共同源码复验。本包不因宿主未接线而免除上述模块实测。交回格式见[共同约束](README.md#交回)；完成后推自己的分支和真实证据，不停在请求push确认。

