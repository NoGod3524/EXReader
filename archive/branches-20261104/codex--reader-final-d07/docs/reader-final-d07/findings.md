# D07 结果与保留失败

本包只检查中文指南的源码可追溯性和链接，不运行产品、SDK 或真机。正文和来源表保持受测字节；本文件及 validation 为验收后的文档封存。

## 保留失败

首轮受测 `989abc10e1cc4cddd69be941c4144648add5b0f3`，run `40215722278` / attempt 1：

- `121236305310` / D07 document audit：success；17 操作组、68 来源引用、16 链接；10 个具名检查全部通过。
- `121236383862` / D07 artifact authentication：failure；错误 `extra or missing payload`。
- 原因：Actions 上传默认排除隐藏目录，源码清单包含的 `inputs/.github/workflows/reader-final-d07.yml` 未进入 ZIP。严格集合检查拒绝该轮，未降低断言。
- 修复：仅对自己的 payload 上传启用 `include-hidden-files: true`，同时让集合不匹配错误列出 missing/extra。新完整源码轮重新执行全部检查；不拼接旧轮成功。
- 保留 payload `12607965267`，23896 字节，API SHA-256 `789ea1625aa54cf1daf8cb5813e09f528d5331bfc591cc1b648fb3900842117d`，到期 `2026-11-24T17:17:29Z`。
- 保留失败 evidence `12606819975`，296 字节，API SHA-256 `22e716bbb934293b0781ba71eccd181498052535a7b02f1bfb66a642c7eb6196`，到期 `2026-11-24T17:17:44Z`。
- 首轮原日志可按上述 run/job 在 GitHub 读取；未删除、替换或重跑该轮。

## 未授予范围

- 六平台安装/发行/签名；没有提供安装包或商店链接。
- 任何 EXReader 程序或 SDK 二进制执行与哈希认证；此包实际执行的是文档检查 Python/Node 程序。
- 固定源全部功能的实际 UI 操作、真实 WebDAV 账号、第三方云盘、真实设备/USB、读屏、性能与跨端互通。
- Apple 移动候选整轮失败仍保持失败，不借 iPad 单叶成功。
- 所有17操作组仍有人工运行步骤待检，具体在 source-inventory 的 manual 字段。
- 尚未确认统一排序菜单、Apple 分类多选整理、六平台文件夹/拖放入口、全库备份导出、通用撤销删书及自动冲突合并。

## root 可执行的下一步

以统一产品源的实际发布构建核对功能开关与入口；完成各平台宿主/真机/账号/恢复验证后再更新对应指南步骤。修正已有 Windows README 的目录内 reader.c 旧描述，由 owner 处理，不在 D07 改原文件。不得将 D07 文档验收解释为产品验收。
