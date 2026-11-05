# G12：Windows 键盘与无障碍审计

先读[共同约束](README.md)，接受其中全部不变项与云端执行限制。
固定实现起点：`f43baf9182d75907c0cb5d6f77048f27bca8c950`。新建独立工作树和分支 `codex/reader-a11y-windows`。
类型：审计；优先级：P1；分发：DeepSeek Harness。

## 文件归属

- `tests/reader_a11y_windows/**`
- `.github/workflows/reader-a11y-windows.yml`
- `docs/READER-A11Y-WINDOWS.md`
- `docs/validation/reader-a11y-windows.json`

除此之外的目录只读。不要修改共享构建、已有工作流或本交接目录。

## 实现与边界

只新增测试，对固定基线真实Win32书架、导入、整理、阅读、标注与已存在的设置流程，用UI Automation和真实键盘审计accessible name/role/state、Tab顺序、可见焦点、弹窗返回焦点及无鼠标路径。
不存在的界面/未实现能力记缺口，不造控件或删用例。给出元素定位、复现步骤、预期/实际和最小修复建议；生产文件仍由G01/root独占。
自动UIA不等于NVDA/真实用户读屏验收；人工读屏未做就保持未验证。

## 云端出口

Windows Actions启动实际宿主并保存原始UIA树、按键轨迹、截图。audit_completed与accessibility_accepted分开；有阻断问题不能accepted=true。
审计范围、问题数与逐项结果匹配，不用“生成了报告”冒充全绿。
同一source/run/attempt逐项验收；参考通过记录不转移到本包源码。任何未覆盖能力继续保持未授予。

## 先读的实际代码

- `tests/windows_host`
- `examples/reader.c`

## 交回

推送功能分支；完整受测SHA、最终纯文档HEAD/差异、run/attempt/job、具名结果、工件ID/字节/digest/有效期、原失败及剩余工作。不要替root合入。

