# D20 最终交回：真实高 DPI 驱动已打通，产品失败原样保留

**驱动/证据交付完成；产品整体及完整对比度验收不通过。** 两个完整 Actions
轮次，未使用第三轮。第二轮真实达到100%、150%、200%，每种尺度都执行
normal/high × default/small四个场景；没有把请求值或重复100%写成高DPI成功。

## 1. 精确源码与程序身份

- 分支：`NoGod3524/EXReader:codex/reader-wave3-d20`。
- 固定seed：`d263ce5228838ac90c0a0dc13a5193d4a7739681`，不是已验收生产BASE。
- 冻结SDK：`edddc463c06ed5731195cdb8f06b2df6dff7699e`。
- **最终受测完整SHA：`b9baf1dfe7be86017d65449fac63a39566683a25`**。
- 受测tree：`72ee3169cf2986115321986aa613e4c3bedccb73`。
- 文档封存：本文件所在独立 `[skip ci]` 提交；其完整远端SHA记入外部
  `D20-status.md`及交回消息，避免自引用。文档提交没有被冒称重新受测。
- 实际 `EXReaderProduct.exe` SHA256：
  `88551b9c7ac17a5445b3dea57c79bf4ccf99fb14ef105ae880485aadba2dbb11`。

同一受测源码fresh构建/安装SDK、product provider、完整原D08模块集和compact
宿主。compact/search/navigation/records/import-organize/preferences ON；raw3、
preference-review OFF。保留真实compile_commands、CMakeCache、Ninja、link map、
installed libraries身份及每次启动的实际program/DLL路径/大小/hash。首进程38个
loaded modules，后续11个进程各37个；不是延迟加载全生命周期认证。

全部本地工作仅源码、文档、Git；语法、负控、构建、夹具、UI/截图、ZIP下载解包
及证据解析均在Actions。Git push缺交互凭据后，使用已授权GitHub Git Data API；
本地和远端tree逐次相同，远端作者回读为Yinuo Xu。没有reset、强推、PR、主线、
tag、Release、SDK或其他owner编辑，也没有创建Codex/电脑任务/子代理。

## 2. 同轮原始工件认证

[最终run 40274548891](https://github.com/NoGod3524/EXReader/actions/runs/40274548891)，
attempt **1**。原生job **121414399649**、strict job **121418295034**均success。

| 原始ZIP | ID | bytes | SHA256 | expiry UTC |
|---|---:|---:|---|---|
| raw |12630341038|30924976|`232e3e67e2935fd5c62dc92110f2b99c83c06a68a50488c48952d4e13cddeba4`|2026-11-25T05:44:07Z|
| summary |12630087222|394367|`91ecb8a10cdaa6aa2e57ce7b92434bb23937a489e8077292681a3be9ef3271c7`|2026-11-25T05:44:42Z|

raw原ZIP在同run strict中下载，核验真实size/digest/expiry、唯一工件名/ID、
source/run/attempt、原生job、每个索引文件、实际程序、编译配置和截图BMP签名。
summary仅确认上传摘要/API元数据，**未递归下载认证**。credential/token扫描
2140个文件/日志输入通过。当前raw保存1622张原始BMP及Settings真实PNG/UIA树，
不是人为缩放的测试图片。所有日志由connector只读查看；未本地下载/解析工件。

## 3. 实际显示能力与恢复

Actions临时Windows Server 2022，session 2，`remote_session=false`。
先按原始1024×768模式保留100%四组回归；之后从真实枚举支持模式选择
1600×1200，`ChangeDisplaySettingsEx` test/apply返回0且真实回读一致。
Settings唯一缩放ComboBox内实际提供100/125/150/175/200；按provider PID
枚举XAML popup并选择150和200，再要求native显示器scale和独立PMv2探针一致。

| 真实场景 | 显示器scale | 独立PMv2 probe DPI | 物理显示 | 真实work area |
|---|---:|---:|---|---|
|100%|100|96|1024×768|`[0,0,1024,728]`|
|150%|150|144|1600×1200|`[0,0,1600,1140]`|
|200%|200|192|1600×1200|`[0,0,1600,1120]`|

高对比正常flags126、高对比flags127，设置均返回true。每组测试前重新回读。
最后实际恢复flags126、100%/96DPI、1024×768、原work area1024×728；mode/scale/
high-contrast恢复检查均通过。不修改用户电脑、不直接改DPI注册表、不重启/注销、
不向目标注入awareness或WM_DPICHANGED、不修改报告的DPI数值。

## 4. 全部命名结果（204项）

**168 pass / 24 fail / 12 pending / 0 error**。每组17项完整执行。

| 场景 | 目标DPI | 初始layout | More | More状态可见 | contrast | 其余12项 |
|---|---|---|---|---|---|---|
|100-normal-default|pass|pass|fail|pass|pending|pass|
|100-normal-small|pass|pass|fail|pass|pending|pass|
|100-high-default|pass|pass|fail|pass|pending|pass|
|100-high-small|pass|pass|fail|pass|pending|pass|
|150-normal-default|fail|fail|fail|pass|pending|pass|
|150-normal-small|fail|pass|pass|pass|pending|pass|
|150-high-default|fail|fail|fail|pass|pending|pass|
|150-high-small|fail|pass|pass|pass|pending|pass|
|200-normal-default|fail|pass|fail|fail|pending|pass|
|200-normal-small|fail|pass|fail|fail|pending|pass|
|200-high-default|fail|pass|fail|fail|pending|pass|
|200-high-small|fail|pass|fail|fail|pending|pass|

其余12项：TXT原生键盘导入/打开、书架/阅读正反Tab遍历、实际前后翻页，
search/directory/records/settings四模态原生可见/启用/模态子孙焦点三样本及退出，
回书架、单列shelf-search关闭焦点、书架/阅读状态native/UIA非空文字与真实像素/
物理边界。输入为SendInput，不使用WM_COMMAND/BM_CLICK代替受测路径。
这不授予搜索结果选择、保存新记录、应用设置等未执行业务功能。

## 5. 交C09的产品缺口

1. **高DPI原生适配未通过：** 八个真实150/200场景目标窗口仍
   `GetDpiForWindow=96`、awareness=0、system_dpi=96；native monitor确为150/200，
   独立probe确为144/192。环境能力缺口已闭合，但不能把Windows bitmap
   virtualization当作原生DPI适配通过。未改变D08原目标DPI断言。
2. **100% More越界（四组）：** 展开外框default `[0,0,1044,728]`、small
   `[0,0,1044,660]`，超过work `[0,0,1024,728]`；page右边1028。
3. **150% default初始及More外框越界（两组）：** `[0,0,1601,1140]`右边
   比真实work1600多1像素；原生测量保留，不放宽容差。small两组More窄范围通过。
4. **200% More与状态不可见（四组）：** 外框`[0,0,1640,1240]`超过真实work
   `[0,0,1600,1120]`；status `[708,1168,892,1212]`位于work下方，且底部超物理
   显示1200。UIA仍报告offscreen=false，不能代替native物理边界。note editor
   `[32,1044,500,1148]`也跨出work，虽然可Tab聚焦；page右边1608/下边1144。

源码定位（只读）：`apps/reader/desktop/windows_compact_ui.inc:109–118
compact_expand`直接将More窗要求至少1060×660；`examples/reader.c:4996–5009`
的最小拖动尺寸钳位并不阻止这次主动扩窗。DPI awareness属Windows产品owner；
D20没有修改owner，没有扩大工作区来覆盖原100%失败。

## 6. 保留pending与历史

每组105个text-bearing控件像素样本，总1260；904个候选颜色对在原始自身client
像素中确实存在，356个未解析。12组完整contrast仍pending：未证明候选色都是
语义文字/背景、ICC转换、全部glyph/focus/selection paint。没有用系统palette比率
或“有不同像素”替代完整contrast。Narrator/NVDA/物理键盘、全部glyph裁切和真实
读屏语音未验收。只认证自动化可观测范围。

CI1完整失败/局限见 `docs/reader-wave3-d20/ITERATION-1.md`：
`8a181bc04075d1cf443c307b4d43970cbb739730`，run`40273388456/1`；
当时150/200尚未实现、100% More已失败，不能追改为通过。
D08`30158c44dcd9ebf27e028b85f60c4fe374b9c90b`、run`40226179285/1`及其
CI1/D02历史失败全部保留。当前seed的shelf-search/default初始窗通过不追溯覆盖旧源。
原D08四个负控、新D20八个负控全部拒绝；旧裁判字节没改。

第三轮不盲跑：第二轮已修复本包驱动并完成全部可执行矩阵，余下为明确产品owner
失败和未宣称的完整contrast/读屏范围。产品源码不在D20写入授权内。

## 7. 接入命令与界限

```sh
git fetch origin codex/reader-wave3-d20
git cherry-pick 8a181bc04075d1cf443c307b4d43970cbb739730
git cherry-pick b9baf1dfe7be86017d65449fac63a39566683a25
# 再cherry-pick交回消息/D20-status.md中的最终[skip ci]文档SHA
```

仅接入D20独占tests/workflow/docs/HANDOFF；原SDK冻结与新宿主候选分开。
当前结果只对应上述完整受测SHA。最终组合源码需root显式组合来源与guard，不得
把当前guard改写成接受任意来源，也不得把这些通过项移植成未测组合的验收。
