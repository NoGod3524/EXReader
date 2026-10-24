# J09：原书与产品元数据只读信息快照

**可立即独立开工 · P1 · 用户手动分发**

先读[共同约束](README.md)，再执行本任务。仓库 `NoGod3524/EXReader`；固定起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`；唯一分支 `codex/reader-book-information`。不要跟随主线或其它工作包HEAD；不要在现有宿主工作树切分支。

## 目标与复用

提供供低频“书籍信息”界面消费的只读快照：产品标题/作者、格式、已验证字节/身份、本机可用性，以及确实可从公开 SDK 获取的属性。

依赖只读：公开 EXReader metadata/source/页数接口；apps/reader/store/native/catalog.h。先阅读固定起点的公开头与已有安装消费者，确认真实签名和线程规则；不得按名字猜接口。其它J包、尚未合入的G包以及四套宿主当前改动都不是前置依赖。

## 必须交付的行为

清楚区分产品字段与解析器字段；不把未知页数/语言/作者填成臆测值，不读 SDK SQL。不将本机 SDK ID 暴露为跨设备身份。深拷贝、上限、取消与来源寿命明确。

公开接口要写清输入/输出、内存归属、线程/重入、错误、取消、提交边界和硬上限。实现可运行的最小原生组件与安装后接入范例，不只交设计或数据结构。

## 允许修改的全部路径

- `apps/reader/book-information/**`
- `tests/reader_book_information/**`
- `.github/workflows/reader-book-information.yml`
- `docs/READER-BOOK-INFORMATION.md`
- `docs/validation/reader-book-information.json`

任务页、共同约束和其它路径由root维护，禁止修改。需要共享API或额外路径时，先交具体缺口，继续不依赖它的工作；不得擅自扩路径或依赖移动分支。

## Actions验收

三桌面平台九格式；云端仅 metadata、本机映射缺失、未知属性、非 ASCII、超长字段、SDK 释放后快照可读、错书身份、取消；独立 public API 比对且前后存储不变。

执行共同约束的源码/保护树/路径守卫、实际安装消费、具名正反例和严格同源工件汇总。不能以成功生成报告等同功能通过；模拟器/桌面/真机和实际音频/朗读等范围分别登记。

## 边界

不实现编辑、不改 metadata 模块或宿主信息弹窗，不重复散列所有书籍。

root负责当前宿主接线与最终共同源码复验。本包不因宿主未接线而免除上述模块实测。交回格式见[共同约束](README.md#交回)；完成后推自己的分支和真实证据，不停在请求push确认。

