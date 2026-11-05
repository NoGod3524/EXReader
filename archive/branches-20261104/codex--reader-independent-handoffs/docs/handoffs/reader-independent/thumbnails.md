# G02：封面、首屏预览与有界缩略图缓存

先读[共同约束](README.md)，接受其中全部不变项与云端执行限制。
固定实现起点：`f43baf9182d75907c0cb5d6f77048f27bca8c950`。新建独立工作树和分支 `codex/reader-thumbnails`。
类型：功能；优先级：P0；分发：Claude Code。

## 文件归属

- `apps/reader/thumbnails/**`
- `tests/reader_thumbnails/**`
- `.github/workflows/reader-thumbnails.yml`
- `docs/READER-THUMBNAILS.md`
- `docs/validation/reader-thumbnails.json`

除此之外的目录只读。不要修改共享构建、已有工作流或本交接目录。

## 实现与边界

可选安装包 EXReaderThumbnails 0.1.0，公开 C ABI。最短路线是 exr_library_blob(cover=1) 或宿主提供的已验证编码封面，经 exr_image_decode/canvas 缩放；PDF/CBZ可借公开 fixed_document 用 exr_fixed_render 生成首屏预览。
借用句柄必须在其 owner 同步调用，不创建线程。封面缺失是正常占位状态；首屏预览须与“作者封面”分开标记。有界EPUB导入不保存封面，禁止私拆ZIP、加载整书来伪造流式封面支持。
缓存身份由已验证原书格式+SHA、输出尺寸和渲染参数决定；明确像素/尺寸/条目/总字节硬上限，LRU淘汰，缓存损坏可重建，原书和用户数据不改。独立缓存文件原子发布；不新建产品schema。
图像解码本身可能分配原图内存，不能把缩略图缓存上限声称为解码器总内存上限。检查尺寸乘法溢出、异常图、透明通道及取消。

## 云端出口

Windows/Linux/macOS installed C11/C++消费者；确定性小图像像素预期、纵横比、alpha、缺失封面、真实PDF/CBZ预览、上限/溢出拒绝、LRU、串书/参数缓存误命中、损坏缓存重建、取消及重开。
独立记录缓存bytes、原解码图bytes和进程RSS；不授予产品性能。输出实际消费者和每项结果。
同一source/run/attempt逐项验收；参考通过记录不转移到本包源码。任何未覆盖能力继续保持未授予。

## 先读的实际代码

- `include/exr/graphics.h`
- `include/exr/library.h`
- `include/exr/document.h`
- `include/exr/render.h`

## 交回

推送功能分支；完整受测SHA、最终纯文档HEAD/差异、run/attempt/job、具名结果、工件ID/字节/digest/有效期、原失败及剩余工作。不要替root合入。

