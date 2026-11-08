# 184 项待查逐项定性

结论针对严格模式；默认宽容结果逐项保持原行为。

| 编号 | 结论 | 具体依据 | 严格退出码 | 宽容退出码 |
|---|---|---|---:|---:|
| directory-001 | 应当报错 | ZIP 字段 local_header_offset@97202 应为 0，实际 1；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-002 | 应当报错 | ZIP 字段 compressed_size@97180 应为 20，实际 21；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-003 | 应当报错 | ZIP 字段 uncompressed_size@97184 应为 20，实际 21；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-008 | 应当报错 | ZIP 字段 local_header_offset@97202 应为 0，实际 2；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-009 | 应当报错 | ZIP 字段 compressed_size@97180 应为 20，实际 22；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-010 | 应当报错 | ZIP 字段 uncompressed_size@97184 应为 20，实际 22；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-015 | 应当报错 | ZIP 字段 local_header_offset@97202 应为 0，实际 3；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-016 | 应当报错 | ZIP 字段 compressed_size@97180 应为 20，实际 23；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-017 | 应当报错 | ZIP 字段 uncompressed_size@97184 应为 20，实际 23；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-022 | 应当报错 | ZIP 字段 local_header_offset@97202 应为 0，实际 4；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-023 | 应当报错 | ZIP 字段 compressed_size@97180 应为 20，实际 24；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-024 | 应当报错 | ZIP 字段 uncompressed_size@97184 应为 20，实际 24；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-029 | 应当报错 | ZIP 字段 local_header_offset@97202 应为 0，实际 5；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-030 | 应当报错 | ZIP 字段 compressed_size@97180 应为 20，实际 25；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-031 | 应当报错 | ZIP 字段 uncompressed_size@97184 应为 20，实际 25；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-036 | 应当报错 | ZIP 字段 local_header_offset@97202 应为 0，实际 6；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-037 | 应当报错 | ZIP 字段 compressed_size@97180 应为 20，实际 26；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-038 | 应当报错 | ZIP 字段 uncompressed_size@97184 应为 20，实际 26；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-043 | 应当报错 | ZIP 字段 local_header_offset@97202 应为 0，实际 7；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-044 | 应当报错 | ZIP 字段 compressed_size@97180 应为 20，实际 27；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-045 | 应当报错 | ZIP 字段 uncompressed_size@97184 应为 20，实际 27；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-050 | 应当报错 | ZIP 字段 local_header_offset@97202 应为 0，实际 8；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-051 | 应当报错 | ZIP 字段 compressed_size@97180 应为 20，实际 28；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-052 | 应当报错 | ZIP 字段 uncompressed_size@97184 应为 20，实际 28；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-057 | 应当报错 | ZIP 字段 local_header_offset@97202 应为 0，实际 9；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-058 | 应当报错 | ZIP 字段 compressed_size@97180 应为 20，实际 29；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-059 | 应当报错 | ZIP 字段 uncompressed_size@97184 应为 20，实际 29；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-064 | 应当报错 | ZIP 字段 local_header_offset@97202 应为 0，实际 10；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-065 | 应当报错 | ZIP 字段 compressed_size@97180 应为 20，实际 30；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-066 | 应当报错 | ZIP 字段 uncompressed_size@97184 应为 20，实际 30；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-071 | 应当报错 | ZIP 字段 local_header_offset@97202 应为 0，实际 11；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-072 | 应当报错 | ZIP 字段 compressed_size@97180 应为 20，实际 31；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-073 | 应当报错 | ZIP 字段 uncompressed_size@97184 应为 20，实际 31；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-078 | 应当报错 | ZIP 字段 local_header_offset@97202 应为 0，实际 12；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-079 | 应当报错 | ZIP 字段 compressed_size@97180 应为 20，实际 32；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-080 | 应当报错 | ZIP 字段 uncompressed_size@97184 应为 20，实际 32；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-085 | 应当报错 | ZIP 字段 local_header_offset@97202 应为 0，实际 13；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-086 | 应当报错 | ZIP 字段 compressed_size@97180 应为 20，实际 33；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-087 | 应当报错 | ZIP 字段 uncompressed_size@97184 应为 20，实际 33；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-092 | 应当报错 | ZIP 字段 local_header_offset@97202 应为 0，实际 14；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-093 | 应当报错 | ZIP 字段 compressed_size@97180 应为 20，实际 34；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-094 | 应当报错 | ZIP 字段 uncompressed_size@97184 应为 20，实际 34；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-099 | 应当报错 | ZIP 字段 local_header_offset@97202 应为 0，实际 15；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-100 | 应当报错 | ZIP 字段 compressed_size@97180 应为 20，实际 35；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-101 | 应当报错 | ZIP 字段 uncompressed_size@97184 应为 20，实际 35；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-106 | 应当报错 | ZIP 字段 local_header_offset@97202 应为 0，实际 16；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-107 | 应当报错 | ZIP 字段 compressed_size@97180 应为 20，实际 36；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-108 | 应当报错 | ZIP 字段 uncompressed_size@97184 应为 20，实际 36；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-113 | 应当报错 | ZIP 字段 local_header_offset@97202 应为 0，实际 17；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-114 | 应当报错 | ZIP 字段 compressed_size@97180 应为 20，实际 37；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-115 | 应当报错 | ZIP 字段 uncompressed_size@97184 应为 20，实际 37；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-120 | 应当报错 | ZIP 字段 local_header_offset@97202 应为 0，实际 18；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-121 | 应当报错 | ZIP 字段 compressed_size@97180 应为 20，实际 38；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-122 | 应当报错 | ZIP 字段 uncompressed_size@97184 应为 20，实际 38；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-127 | 应当报错 | ZIP 字段 local_header_offset@97202 应为 0，实际 19；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| directory-128 | 应当报错 | ZIP 字段 compressed_size@97180 应为 20，实际 39；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复 | 1 | 0 |
| mimetype-001 | 应当报错 | 内容为 application/damaged-epub-001+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-002 | 应当报错 | 内容为 application/damaged-epub-002+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-003 | 应当报错 | 内容为 application/damaged-epub-003+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-004 | 应当报错 | 内容为 application/damaged-epub-004+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-005 | 应当报错 | 内容为 application/damaged-epub-005+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-006 | 应当报错 | 内容为 application/damaged-epub-006+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-007 | 应当报错 | 内容为 application/damaged-epub-007+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-008 | 应当报错 | 内容为 application/damaged-epub-008+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-009 | 应当报错 | 内容为 application/damaged-epub-009+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-010 | 应当报错 | 内容为 application/damaged-epub-010+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-011 | 应当报错 | 内容为 application/damaged-epub-011+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-012 | 应当报错 | 内容为 application/damaged-epub-012+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-013 | 应当报错 | 内容为 application/damaged-epub-013+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-014 | 应当报错 | 内容为 application/damaged-epub-014+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-015 | 应当报错 | 内容为 application/damaged-epub-015+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-016 | 应当报错 | 内容为 application/damaged-epub-016+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-017 | 应当报错 | 内容为 application/damaged-epub-017+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-018 | 应当报错 | 内容为 application/damaged-epub-018+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-019 | 应当报错 | 内容为 application/damaged-epub-019+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-020 | 应当报错 | 内容为 application/damaged-epub-020+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-021 | 应当报错 | 内容为 application/damaged-epub-021+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-022 | 应当报错 | 内容为 application/damaged-epub-022+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-023 | 应当报错 | 内容为 application/damaged-epub-023+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-024 | 应当报错 | 内容为 application/damaged-epub-024+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-025 | 应当报错 | 内容为 application/damaged-epub-025+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-026 | 应当报错 | 内容为 application/damaged-epub-026+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-027 | 应当报错 | 内容为 application/damaged-epub-027+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-028 | 应当报错 | 内容为 application/damaged-epub-028+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-029 | 应当报错 | 内容为 application/damaged-epub-029+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-030 | 应当报错 | 内容为 application/damaged-epub-030+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-031 | 应当报错 | 内容为 application/damaged-epub-031+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-032 | 应当报错 | 内容为 application/damaged-epub-032+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-033 | 应当报错 | 内容为 application/damaged-epub-033+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-034 | 应当报错 | 内容为 application/damaged-epub-034+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-035 | 应当报错 | 内容为 application/damaged-epub-035+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-036 | 应当报错 | 内容为 application/damaged-epub-036+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-037 | 应当报错 | 内容为 application/damaged-epub-037+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-038 | 应当报错 | 内容为 application/damaged-epub-038+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-039 | 应当报错 | 内容为 application/damaged-epub-039+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-040 | 应当报错 | 内容为 application/damaged-epub-040+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-041 | 应当报错 | 内容为 application/damaged-epub-041+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-042 | 应当报错 | 内容为 application/damaged-epub-042+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-043 | 应当报错 | 内容为 application/damaged-epub-043+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-044 | 应当报错 | 内容为 application/damaged-epub-044+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-045 | 应当报错 | 内容为 application/damaged-epub-045+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-046 | 应当报错 | 内容为 application/damaged-epub-046+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-047 | 应当报错 | 内容为 application/damaged-epub-047+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-048 | 应当报错 | 内容为 application/damaged-epub-048+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-049 | 应当报错 | 内容为 application/damaged-epub-049+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-050 | 应当报错 | 内容为 application/damaged-epub-050+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-051 | 应当报错 | 内容为 application/damaged-epub-051+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-052 | 应当报错 | 内容为 application/damaged-epub-052+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-053 | 应当报错 | 内容为 application/damaged-epub-053+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-054 | 应当报错 | 内容为 application/damaged-epub-054+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-055 | 应当报错 | 内容为 application/damaged-epub-055+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-056 | 应当报错 | 内容为 application/damaged-epub-056+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-057 | 应当报错 | 内容为 application/damaged-epub-057+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-058 | 应当报错 | 内容为 application/damaged-epub-058+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-059 | 应当报错 | 内容为 application/damaged-epub-059+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-060 | 应当报错 | 内容为 application/damaged-epub-060+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-061 | 应当报错 | 内容为 application/damaged-epub-061+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-062 | 应当报错 | 内容为 application/damaged-epub-062+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-063 | 应当报错 | 内容为 application/damaged-epub-063+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-064 | 应当报错 | 内容为 application/damaged-epub-064+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-065 | 应当报错 | 内容为 application/damaged-epub-065+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-066 | 应当报错 | 内容为 application/damaged-epub-066+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-067 | 应当报错 | 内容为 application/damaged-epub-067+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-068 | 应当报错 | 内容为 application/damaged-epub-068+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-069 | 应当报错 | 内容为 application/damaged-epub-069+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-070 | 应当报错 | 内容为 application/damaged-epub-070+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-071 | 应当报错 | 内容为 application/damaged-epub-071+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-072 | 应当报错 | 内容为 application/damaged-epub-072+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-073 | 应当报错 | 内容为 application/damaged-epub-073+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-074 | 应当报错 | 内容为 application/damaged-epub-074+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-075 | 应当报错 | 内容为 application/damaged-epub-075+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-076 | 应当报错 | 内容为 application/damaged-epub-076+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-077 | 应当报错 | 内容为 application/damaged-epub-077+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-078 | 应当报错 | 内容为 application/damaged-epub-078+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-079 | 应当报错 | 内容为 application/damaged-epub-079+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-080 | 应当报错 | 内容为 application/damaged-epub-080+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-081 | 应当报错 | 内容为 application/damaged-epub-081+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-082 | 应当报错 | 内容为 application/damaged-epub-082+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-083 | 应当报错 | 内容为 application/damaged-epub-083+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-084 | 应当报错 | 内容为 application/damaged-epub-084+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-085 | 应当报错 | 内容为 application/damaged-epub-085+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-086 | 应当报错 | 内容为 application/damaged-epub-086+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-087 | 应当报错 | 内容为 application/damaged-epub-087+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-088 | 应当报错 | 内容为 application/damaged-epub-088+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-089 | 应当报错 | 内容为 application/damaged-epub-089+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-090 | 应当报错 | 内容为 application/damaged-epub-090+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-091 | 应当报错 | 内容为 application/damaged-epub-091+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-092 | 应当报错 | 内容为 application/damaged-epub-092+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-093 | 应当报错 | 内容为 application/damaged-epub-093+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-094 | 应当报错 | 内容为 application/damaged-epub-094+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-095 | 应当报错 | 内容为 application/damaged-epub-095+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-096 | 应当报错 | 内容为 application/damaged-epub-096+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-097 | 应当报错 | 内容为 application/damaged-epub-097+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-098 | 应当报错 | 内容为 application/damaged-epub-098+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-099 | 应当报错 | 内容为 application/damaged-epub-099+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-100 | 应当报错 | 内容为 application/damaged-epub-100+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-101 | 应当报错 | 内容为 application/damaged-epub-101+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-102 | 应当报错 | 内容为 application/damaged-epub-102+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-103 | 应当报错 | 内容为 application/damaged-epub-103+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-104 | 应当报错 | 内容为 application/damaged-epub-104+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-105 | 应当报错 | 内容为 application/damaged-epub-105+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-106 | 应当报错 | 内容为 application/damaged-epub-106+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-107 | 应当报错 | 内容为 application/damaged-epub-107+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-108 | 应当报错 | 内容为 application/damaged-epub-108+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-109 | 应当报错 | 内容为 application/damaged-epub-109+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-110 | 应当报错 | 内容为 application/damaged-epub-110+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-111 | 应当报错 | 内容为 application/damaged-epub-111+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-112 | 应当报错 | 内容为 application/damaged-epub-112+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-113 | 应当报错 | 内容为 application/damaged-epub-113+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-114 | 应当报错 | 内容为 application/damaged-epub-114+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-115 | 应当报错 | 内容为 application/damaged-epub-115+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-116 | 应当报错 | 内容为 application/damaged-epub-116+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-117 | 应当报错 | 内容为 application/damaged-epub-117+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-118 | 应当报错 | 内容为 application/damaged-epub-118+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-119 | 应当报错 | 内容为 application/damaged-epub-119+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-120 | 应当报错 | 内容为 application/damaged-epub-120+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-121 | 应当报错 | 内容为 application/damaged-epub-121+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-122 | 应当报错 | 内容为 application/damaged-epub-122+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-123 | 应当报错 | 内容为 application/damaged-epub-123+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-124 | 应当报错 | 内容为 application/damaged-epub-124+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-125 | 应当报错 | 内容为 application/damaged-epub-125+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-126 | 应当报错 | 内容为 application/damaged-epub-126+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-127 | 应当报错 | 内容为 application/damaged-epub-127+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
| mimetype-128 | 应当报错 | 内容为 application/damaged-epub-128+zip，应精确为 application/epub+zip；严格模式拒绝 | 1 | 0 |
