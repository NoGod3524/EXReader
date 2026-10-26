# GTK team24 验收记录

团队起点：`05c8494eb8320c22b9e7b439cca82e21bc36a461`，分支 `codex/team24-gtk`。原 C10 guard 的 seed 仍为 `d263ce5228838ac90c0a0dc13a5193d4a7739681`；本轮没有重置旧失败记录或放宽 SDK、原 1710 项及 CPU 预算。

## 保留的先前执行

| run / attempt | source | 实际结果 |
| --- | --- | --- |
| 40237525525 / 1 | 96270a2b478b673eb45b7e2467e2e2acb6b64a88 | 共同 GTK 轮次失败：G13 `shelf_tab_stops_named`；后续身份认证失败保留 |
| 40273627779 / 1 | 5892edd76b6d4919cf4e1f3d57f6c20e8ad75dc0 | C10 失败 |
| 40274220118 / 1 | bb82933ef9e9e5ad43ccaf3cfc398fcdf8bbad47 | C10 取消 |
| 40274396894 / 1 | 05c8494eb8320c22b9e7b439cca82e21bc36a461 | C10 失败：session 在 sync 安装前配置，找不到 EXReaderSync；未产出程序，认证随之失败 |

截至 team24 开始读取时，上述运行均已结束。team24 允许的新完整轮次另计，最多两次；只有父代理提交并启动完整 Actions。

## 本队补充的验收

- 后端真实 owner probe：字体候选取消后释放 lease、候选字体可删除、旧阅读器仍能产生并接受下一页；标注取消丢弃预览，确认绑定已检查的 snapshot，即使原路径文件随后被修改也不会导入另一份未检查的内容。
- 真实 GTK UI：保留现有十项五模块流程；字体文件异常后比较 book/part/page/start/end/frame_generation，随后真实 Next/Previous 验证阅读可用；同步只读详情关闭再打开须保持文本；预览对话框须为模态且持有焦点。
- 原 GTK compact45、G13 十项、搜索、目录、阅读记录和批量导入 driver 保持原字节。身份检查要求每份报告的业务通过字段、source/run/attempt、实际程序 SHA256 一致，拒绝 diagnostic-only 报告。
- `g13_diagnostic.py` 包装原 G13 driver；原 `bus.name` 返回值原样送进原断言。空名 focused toggle 的直接 AT-SPI 读取、异常和独立 raw D-Bus focused Name 留档，不清 cache、不把诊断重读值用于通过断言。与宿主焦点时 ATK 名称日志对照定位产品或观察问题。
- Actions 取得本轮原 ZIP 后，identity 的 `--archive` 核对 ZIP 实际 SHA256 与 GitHub API digest、实际字节数与 API size；再核对两个打包程序和七份业务报告。

本机未运行构建、测试、语法检查、生成夹具、截图、benchmark 或工件下载/解包/解析。新增断言是否通过必须以新 Actions 结果填写；此文档不宣称六平台完成、真机验证或真实读屏验收。

## team24 新轮次

尚待父代理登记 source、run/attempt、各 job 真实结论、原 ZIP 身份、实际程序身份、失败与未测范围。
