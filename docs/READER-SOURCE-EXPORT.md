# SDK原件交给同步worker

现有可选 `EXReaderSideload` 新增 `exr_sideload_export_original`，默认reading SDK构建
不加入此模块。它只调用已安装SDK的公开 `exr_library_source`，不读SDK表或修改SDK。

宿主在SDK owner上按产品目录中的本机映射取得book_id，传入app私有目录内的新UTF-8
目标路径。导出使用64KiB复制缓冲、128MiB上限，可通过原options降低；不解析原件，
不整本分配。临时文件与目标在同目录，完成写入及刷新后释放SDK source，再原子发布。
Windows使用不替换目标的MoveFileEx，POSIX使用同文件系统link；已存在或并发创建的
目标均不覆盖。仅成功返回已发布字节数，所有失败返回零并清理本次创建的临时文件。

源读取失效、短缺、写入失败和取消均不能发布部分原件。回调在调用worker上运行，
不能重入SDK owner。发布后的成功结果优先，宿主随后才将稳定不可变的文件路径交给
网络worker；网络模块继续核对全局book_key对应的长度和SHA-256，条件发布并回读后
才ack。此导出本身不声称验证了全局book_key，也不启动网络、同步或metadata投影。

进程在发布前被终止可能留下未引用的 `.exr-export-` 临时文件；原SDK原件保留。
宿主管理app私有目录及未引用临时文件，不得把未成功返回的文件排入上传队列。

候选在 `reader-reading-v2.yml` 的两平台SDK作业独立安装并编译C/C++消费者，
验证TXT/EPUB/PDF/CBZ原件、Unicode路径、多块读取、取消、限额、写入失败、
竞争目标不覆盖、第二连接使source失效、SDK关闭后文件可用，共14项。
严格汇总核对同次报告和四格式原件SHA-256。当前尚待该候选云端结果。
