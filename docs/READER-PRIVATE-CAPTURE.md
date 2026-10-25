# 桌面私有 native capture codec

状态：待云端验证。仅 app-private pending capture 数据编码，不是公共 wire、SDK 接口或实际宿主验收。

单个C11/C++兼容 `apps/reader/desktop/reading_capture_bytes.h` 只依赖C标准库及 `reader_reading_state.h` 公开类型。encode/decode失败保持调用者输出原字节，成功后输出归调用者；编码缓冲区用 `reader_private_capture_free`，解码字段由malloc分配，兼容 `reader_rs_record_free`。替换成功前，调用者负责释放旧输出。

私有magic为8字节 `EXRPCAP\0`，随后小端u32：format=1、writer=1/2/3、mode、reserved=0；小端u64：part/page/start/end。chapter/path/page_id/exact/prefix/suffix六blob各为present u8、length u32和原始字节；NULL为0/0，非NULL空值为1/0，解码时各分配1字节安全终止符。writer3仅接受fixed模式；fixed selectors只读取显式size，保留NUL与任意字节；其他blob为C文本，decode拒绝计数范围内的NUL。encode的C字符串以第一个终止符为界，不读取其后的对象外字节。

每blob上限65536B，整体上限1MiB。拒绝未知magic/format/writer/mode、reserved非零、坏tag、NULL+非零长度、截断、尾随、倒置范围、非NULL exact与range长度不一致、size_t不可表示数值和过长数据。私有codec不判定UTF-8、SDK真实性、parser、书籍身份或公共wire可表示性；这些保留给宿主及现有公开模块。has_location=1只描述存在capture数据，NULL exact不授予导航或恢复。

旧Windows `EXRRD001` 与GTK keyfile均拒绝识别；旧pending解析留各自宿主。delete/NOTE_TEXT的无capture形态也留pending外层，不生成伪造SDK capture。

云端入口 `reader-private-capture.yml`：Windows与Linux真实C11/C++消费者；Linux额外ASan/UBSan/Leak检查及真实32位C/C++溢出检查。七组golden由独立Python结构模型生成，与八个消费者逐字节相等；所有截断边界、恶意length/tag、NULL/empty组合、非终止fixed缓冲、上限和每个部分malloc失败均检查。仅使用仓库公开头，不链接SDK或raw模块，不授予SDK/宿主/公共wire能力。
