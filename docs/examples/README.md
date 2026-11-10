# SDK 文档示例

这里的 15 个 `.c` 文件分别对应 [API.md](../API.md) 的 15 个模块；文档内的完整示例与文件逐字校验。
每个文件有独立 `main`，只使用公开头文件和 C11 标准库。带路径参数的示例要求 UTF-8 参数；
Windows GUI 宿主应从宽字符路径转换为 UTF-8 后传给 SDK。

在仓库根目录运行（需要 CMake、C11 编译器、Python 3）：

```sh
cmake -S . -B build/sdk-docs -DCMAKE_BUILD_TYPE=Release -DEXR_BUILD_TESTS=ON -DEXR_BUILD_TOOLS=OFF
cmake --build build/sdk-docs --config Release --parallel 4
ctest --test-dir build/sdk-docs -C Release -R '^sdk-doc-' --output-on-failure
python tools/check_sdk_docs.py
```

默认完整组件构建会编译、链接 15 个可执行文件（`exreader-doc-*`），用现有测试样本运行 15 个 smoke，
另加 1 个覆盖/签名/示例一致性检查。GCC/Clang 使用 `-Wall -Wextra -Wpedantic -Werror`，MSVC 使用 `/W4 /WX`。
`EXR_FULL_TESTS` 要求 audio/library/textindex/PDF/PDF-edit 组件全部启用；裁剪 preset 不运行这套完整示例。
PR 现有 Native C engine 工作流使用完整组件，因此会自动构建和执行，无需手动触发工作流。

| 文件 / 模块 | 直接运行参数 | 观察结果 |
|---|---|---|
| `base.c` 基础 | 无 | 版本、ABI、视口像素尺寸 |
| `document.c` 文档 | 无 | 宿主构造的规范化正文 |
| `formats.c` 格式 | 无 | HTML 内存解析结果 |
| `pagination.c` 分页 | `font.ttf` | 第 0 页缓存与扫描字节数 |
| `render.c` 渲染 | `font.ttf output.png` | RGBA/stride 与图片文件 |
| `font.c` 字体与文字 | `font-directory` | 管理器创建的回退链长度 |
| `search.c` 搜索 | 无 | UTF-8 字节命中区间 |
| `annotation.c` 标注 | 无 | JSON 导出、导入和锚点恢复 |
| `toc.c` 目录 | `book.epub` | 目录级别、part、标题 |
| `library.c` 书库 | 无 | 内存 SQLite 导入与书单 |
| `graphics.c` 图形 | 无 | canvas 位图所有权转移 |
| `dictionary.c` 字典 | `book.ifo word` | 匹配词和释义 |
| `textindex.c` 全文索引 | 无 | 派生全文库查询 |
| `pdf.c` 固定版面与 PDF | `input.pdf output.png` | 第一页 96 DPI 渲染 |
| `audio.c` 音频 | 无 | 宿主时间线定位；不打开音频设备 |

字典 smoke 复用 `tests/check_dictionary.py` 的小型二进制样本生成器；不依赖用户词典。
图片写在构建目录中。示例返回 0 表示调用成功，1 表示 SDK 错误，2 表示参数用法错误。
`textindex.c` 在明确禁用全文索引时打印不可用并返回 0；本次验收使用启用的索引构建。

本机编译完整输出见 [compile-output.txt](compile-output.txt)，实际运行输出见 [test-output.txt](test-output.txt)，
机器统计及当前 DLL 符号清单见 [verification.json](verification.json)。本机配置保留所有独立组件，
关闭可选 WebP/TIFF/AVIF/JPX 解码器；这些示例不依赖上述解码器，能力矩阵仍逐项标出构建条件。
