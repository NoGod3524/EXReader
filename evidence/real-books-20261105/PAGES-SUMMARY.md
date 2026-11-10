# 15本×5位置抽样渲染 · 2026-11-05

渲染调用 75 次；成功 75，失败 0。未重试；没有导出PNG或正文。

- 复用修复后的 SDK DLL，SHA-256 `0ce5c7dfb41eb139590a65001257cf6c8d465a845d0798a40347ed5a4770875b`；原15本去重清单与输入SHA-256不变。
- 可重排格式：720×1040，font_size=28，margin=36，line_height=1.5，paragraph_spacing=10；Arial，保留书内CSS，不加user_css。与原Pass A参数一致，不使用1280×800/18px视觉导出的页码。
- PDF使用原生固定页与 min(1,720/max(width,height)) 比例；页数为固定页数。
- 全书页数先由同一参数下的pager计数，不渲染计数页；然后只调用5次栅格化。EPUB页码跨所有parts连续；MOBI为单document。
- page_index从0起算。N页时依次取0、floor((N−1)/4)、floor((N−1)/2)、floor(3(N−1)/4)、N−1；pos对应first/25%/50%/75%/last。
- render_ms用QueryPerformanceCounter只包裹颜色渲染/固定页渲染API，不含打开、分页、PNG编码或文件输出。同一本在同一进程中测5页，字体和系统缓存未重置，均为单次测量。
- DLL为已保留的本地EPUB重点构建，包含基础PDF；可选PDF密码/JPX/ICC、WebP/TIFF/AVIF及音频/数据库组件未启用。本轮未改构建或产品代码，也不把结果称作完整发行包矩阵。

最慢一次：`The Autobiography of Malcolm X. (Malcolm X, Alex Haley) (z-library.sk, 1lib.sk, z-lib.sk).pdf`，pos=50%，page_index=139，53.741800ms。

## 同书最慢/最快 >10

| 文件 | 最快位置/index | 最快ms | 最慢位置/index | 最慢ms | 比值 |
| --- | --- | ---: | --- | ---: | ---: |
| How Does It Feel to Be a Problem Being Young and Arab in America (Moustafa Bayoumi) (z-library.sk, 1lib.sk, z-lib.sk).epub | last/479 | 0.653300 | first/0 | 50.034900 | 76.588 |
| A Raisin in the Sun (Lorraine Hansberry) (z-library.sk, 1lib.sk, z-lib.sk).epub | last/353 | 0.840100 | first/0 | 16.640100 | 19.807 |
| The Fire This Time A New Generation Speaks about Race (Jesmyn Ward) (z-library.sk, 1lib.sk, z-lib.sk).epub | last/313 | 1.295300 | first/0 | 20.439800 | 15.780 |
| Black Boy (Richard Wright) (z-library.sk, 1lib.sk, z-lib.sk).epub | last/968 | 1.890700 | first/0 | 28.321100 | 14.979 |
| Born a Crime (Trevor Noah) (z-library.sk, 1lib.sk, z-lib.sk).epub | last/395 | 1.318700 | first/0 | 17.045100 | 12.926 |
| I Know Why the Caged Bird Sings (Maya Angelou) (z-library.sk, 1lib.sk, z-lib.sk).epub | 50%/312 | 0.980100 | first/0 | 11.618100 | 11.854 |
| The Fire Next Time (James Baldwin) (z-library.sk, 1lib.sk, z-lib.sk).epub | last/186 | 1.771500 | first/0 | 17.738100 | 10.013 |

## 失败项

无。

本轮未在交互桌面上创建任何可见窗口。编译及CLI均以Start-Process -WindowStyle Hidden -Wait执行、输出重定向；没有GUI、窗口操作、PNG或正文入库。
