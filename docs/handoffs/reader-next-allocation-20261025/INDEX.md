# 本轮17包

先读[共同约束](README.md)，每包独立路径和分支。Dot七包已独立写完，用户手动投放；Claude与DeepSeek由root后台分发。

| 接收方 | 包 | 工作 |
| --- | --- | --- |
| Claude | [C04](C04.md) | 真实RTF兼容性候选修复 |
| Claude | [C05](C05.md) | Windows FB2查找差异根因与修复 |
| Claude | [C06](C06.md) | raw3可移植标注导入/导出配套模块 |
| Claude | [C07](C07.md) | 同源Android↔Apple双向记录协议联验 |
| Claude | [C08](C08.md) | Android原APK数据的独立公开SDK回读 |
| DeepSeek | [S13](S13.md) | CBZ前导斜杠的安全兼容候选 |
| DeepSeek | [S14](S14.md) | 既有字体库接入SDK3.41安装图 |
| DeepSeek | [S15](S15.md) | 既有原件导出接入SDK3.41安装图 |
| DeepSeek | [S16](S16.md) | 跳转历史raw3显式兼容 |
| DeepSeek | [S17](S17.md) | 同步状态视图raw家族兼容 |
| Dot | [D08–D14](../reader-dot-final-followups/INDEX.md) | 七个独立UI/安全/稳定性包，用户手动投放 |

Claude使用Sonnet5.5/medium；DeepSeek使用V4.1 Flash1017/high/PTC；两者在自己worktree内完全权限。
权限不扩大本页的写入范围，也不授权发布或修改冻结SDK。
