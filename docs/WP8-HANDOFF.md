# WP8：COLRv1与SVG字体完整交接

## 工作目录与职责

- 分支：`codex/wp8-color-fonts`。
- 工作目录：`C:/Users/Oscar/.codex/worktrees/wp8-color-fonts/EXReader`。
- 独立构建目录前缀：`C:/Users/Oscar/exr-wp8-`；不得复用主线或其他工作包的构建目录。
- 实现并验收完整WP8；主线负责WP6、兼容失败分类与WP16集成。
- 先读 `docs/HANDOFF.md`、`docs/SUPPORT_MATRIX.md`、`docs/SDK_COMPATIBILITY.md`、`tools/layers.json`。

## 必须完成的出口

1. 冻结COLRv1 paint类型矩阵，覆盖各类型正/反例、组合、变换、渐变、复合、palette/前景色及所声明的可变行为。
2. paint图循环、深度、节点/工作量、内存、取消及失败所有权须有明确限制与回归。
3. 冻结SVG字体元素、属性和资源子集；禁止外部访问，明确拒绝不支持行为，保持有界解析/绘制。
4. 至少30个有效且有区分度的渲染场景，与固定版本独立参考比较；记录字体、参考程序、输入和输出散列。
5. 横排/竖排、透明度、选择/命中和页级恢复不退化；现有COLRv0、sbix、CBDT、cmap14继续通过。
6. 逐项解释参考差异，不扩大既有容差，不把简单填色或截图存在当作整包完成。

## 实现边界与协作

- 负责彩色字体解析、paint遍历、SVG字体子集和对应绘制、专属测试及参考工具。
- WP7负责文字脚本塑形与OpenType分类；共用字体入口/内部结构的变更先列明接口与文件，减少交叉修改。
- 复用现有FreeType、Expat和画布/path/paint接口；新增运行依赖须说明必要性、固定版本/散列和许可。
- 不重构主线文档/分页/表格路径，不顺带扩展普通SVG文档格式或PDF工作包。
- 可以在本分支增加必要CMake/分层清单条目，保持公共文件改动集中。
- C11、MIT、ABI1/schema6保持；既有无大小标记公开结构不得改布局，新接口说明所有权与兼容性。
- 主线集成时统一分配SDK/组件版本，本分支不独立修改全局版本。

## 验证与交付

- 独立构建并运行专项，引擎改变后运行完整适用测试；默认/裁剪安装消费继续可用。
- 保存所有原始参考、差异、失败和预算证据，精确绑定源码、字体、程序及依赖散列。
- Windows、本包专项、Linux sanitizer及图像参考分别记录，不互相代替。
- 保存 `docs/validation/wp8-*.json`、paint/SVG支持矩阵及使用示例，只更新本包状态。
- 用本地提交交付：提交SHA列表、变更文件、逐项验收结果、证据路径和未满足项。
- 主线负责合并、跨包回归与最终发行；不要自行合并或推送到`codex/framework`。
- 对话只引用文件路径，不粘贴崩溃栈、fuzz输入细节或攻击性描述。

## 当前基线

SDK3.38.1，核心3.37.1，ABI1/schema6。当前彩色字体支持COLRv0/CPAL、sbix、CBDT/CBLC、cmap14。
FreeType固定VER-2-15-0且HVF关闭；依赖缓存`C:/Users/Oscar/exr-deps`只读复用。
原生画布已有大小标记的paint源与alpha/shape/opacity语义，复用前先核对相关接口及包装转发规则。
