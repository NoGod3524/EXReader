# J01：WebDAV 选书下载与侧载导入

**可立即独立开工 · P0 · 用户手动分发**

先读[共同约束](README.md)，再执行本任务。仓库 `NoGod3524/EXReader`；固定起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`；唯一分支 `codex/reader-webdav-import`。不要跟随主线或其它工作包HEAD；不要在现有宿主工作树切分支。

## 目标与复用

把已有目录浏览、选中远端文件、下载到私有 staging、SDK owner 上导入组成一个独立适配包。网络与 SDK 阶段显式分离，不拿 SDK 指针进入网络 worker，不写产品目录。

依赖只读：extras/webdav/include/exr_webdav.h；extras/sideload/include/exr_sideload.h。先阅读固定起点的公开头与已有安装消费者，确认真实签名和线程规则；不得按名字猜接口。其它J包、尚未合入的G包以及四套宿主当前改动都不是前置依赖。

## 必须交付的行为

复用现有 HTTPS、同源凭据和原子下载；远端名称仅展示，不能变成本地路径。以公开侧载结果返回 committed/created/book_id；32 MiB 重排、128 MiB 流式上限沿用原契约。重复书不能被失败清理删除。

公开接口要写清输入/输出、内存归属、线程/重入、错误、取消、提交边界和硬上限。实现可运行的最小原生组件与安装后接入范例，不只交设计或数据结构。

## 允许修改的全部路径

- `apps/reader/cloud-import/**`
- `tests/reader_webdav_import/**`
- `.github/workflows/reader-webdav-import.yml`
- `docs/READER-WEBDAV-IMPORT.md`
- `docs/validation/reader-webdav-import.json`

任务页、共同约束和其它路径由root维护，禁止修改。需要共享API或额外路径时，先交具体缺口，继续不依赖它的工作；不得擅自扩路径或依赖移动分支。

## Actions验收

三桌面平台真实 TLS；九格式、Unicode、同名不同内容、下载后损坏、重定向/证书/401/长度错误、阶段间取消、提交后取消、短读、失败临时文件清理；独立 SDK 回读原书。

执行共同约束的源码/保护树/路径守卫、实际安装消费、具名正反例和严格同源工件汇总。不能以成功生成报告等同功能通过；模拟器/桌面/真机和实际音频/朗读等范围分别登记。

## 边界

不新增网络后端、账号库、自动同步、宿主界面或产品映射。

root负责当前宿主接线与最终共同源码复验。本包不因宿主未接线而免除上述模块实测。交回格式见[共同约束](README.md#交回)；完成后推自己的分支和真实证据，不停在请求push确认。

