# D20 第一轮原始结果（不改写）

受测完整 SHA `8a181bc04075d1cf443c307b4d43970cbb739730`；tree
`b463a77764b2f1ee5364c140a7e441d731be2a4d`。
[Run 40273388456](https://github.com/NoGod3524/EXReader/actions/runs/40273388456)，attempt 1。
原生 job `121410888115` 与 strict job `121412744323` 均成功。

原始 raw ZIP `12629078502`，22,221,637 bytes，SHA256
`0e45ae18a2093816181a97e77cbd2761cefa87dda588e6628d2783194bb9bb7a`，
有效期 `2026-11-25T05:23:54Z`。同轮 strict 在 Actions 下载原 ZIP 并验证全部
索引文件、实际程序及来源/轮次。原程序 SHA256
`4762a945d40251458b73ee7f11c71cb942733278349255379c4ce4f597709fbc`。
summary ZIP `12630045007`，135,193 bytes，SHA256
`1d2ab41a2edeb0fd7e81764d728e89dd91f4ed3e956ebfc893144f84896af21b`，
有效期 `2026-11-25T05:24:10Z`；summary 为上传摘要/API 元数据，未递归下载验证。

## 原始观测

- 实际 Windows Server 2022、session 2、remote_session=false；显示1024×768，
  实际工作区1024×728，显示器100%、独立PMv2探针96，目标程序96/awareness0。
- 四个100%正常/高对比/default/small场景全部完成，各17个命名结果：15 pass、
  More 1 fail、全局contrast 1 pending。每场景135张BMP、105控件像素样本、
  75个可测候选颜色对（其余30未解析），不据此声称完整文字/焦点对比度合规。
- 启动边界、书架/阅读键盘遍历、TXT导入打开、翻页往返、四模态进出焦点、
  状态可见/可达证据、回书架及单列shelf-search焦点均通过该窄观测。
- 高对比真实flags126→127，finally恢复126；scale恢复100。
- More原始失败：Alt+V、M展开后默认外框`[0,0,1044,728]`、small
  `[0,0,1044,660]`超出工作区`[0,0,1024,728]`；阅读控件右边为1028。
  note editor Tab可达、原生focus visible/enabled/descendant，收起焦点也正确。
  这是未修改的Windows产品owner问题，交C09，不放宽断言。
- 150/200各四个场景未执行，全部pending；没有重复100%的伪高DPI结果。
  Settings真实enabled缩放ComboBox存在，ID
  `SystemSettings_Display_Scaling_ItemSizeOverride_ComboBox`，但第一次仅在主窗
  子树枚举没有找到目标选项，因此**尚不能断言该runner绝对缺少高DPI能力**。
- 实际支持模式包括1600×1200与1920×1080。第二轮将保留原100%回归，再用
  枚举模式真实切换，并枚举同Settings进程的popup选择项。不是修改图片或结果数值。
- 原4个D08负控及8个D20负控均拒绝；credential扫描831项通过。

不迁移第一轮通过结果到第二轮；第二轮必须同源重新构建/执行/认证。
