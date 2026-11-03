# CI-DEPS-001 — Apple product staging omission

定性：打包遗漏（产品依赖 staging 步骤遗漏）。归属 P 的打包修复，R 候选证据轮一起验证；不进入 F07 功能清单。本次只登记，不修产品、不新增运行。

已有失败：run 41707789690 / apple-mobile job 126167587852，步骤 Build and run the iPhone and iPad reference host，首条错误 Missing installed Apple product dependency，首个缺失路径 stage/iphonesimulator/include/exreader-product。

静态依据（95100501 与 21add50a）：
- tools/apple_swift.py 的 flags() 原已要求 product/include/exreader-product 与产品静态库；tools/build_apple_host.py 原已无条件调用 product_flags。这不是 V 或待落地 provider 新引入的构建依赖。
- .github/workflows/native.yml 的 apple-mobile 仅构建、安装根 SDK 到 stage/iphoneos 和 stage/iphonesimulator，随后直接调用 build_apple_host.py，未调用产品构建安装步骤。
- tools/build_apple_product.py 提供产品构建安装；apps/reader/store/native/CMakeLists.txt 安装产品头至 include/exreader-product，并安装产品静态库。

当前证据证明依赖安装链缺步骤；未执行补包后的构建，不能据此声称所有后续构建依赖均已满足。不得为此单独申请 CI；修复随 P，验证随 R 候选证据轮。
