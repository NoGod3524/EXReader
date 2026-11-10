# 产物 SHA-256 与导出数

以下来自实际文件重新读取；命令为 python -B tools/platforms/inventory.py evidence/platforms2-20261109/artifact-inputs.json --out evidence/platforms2-20261109/artifacts.json。所有引擎库均包含既有 389 项 ABI 契约；导出总数包括 vendor/internal 符号。不同功能配置的总数不要求相等。

| 平台 / 架构 | 产物 | 来源 SHA | 导出数 | SHA-256 |
|---|---|---|---:|---|
| Android / arm64-v8a | libexreader.so | bd15cddb | 2800 | 4853cbbd81d3c51b63de3e5aa6c83f4cece58dd6f79bd39acb1aa9c3032adafa |
| Android / arm64-v8a | libexreader_jni.so | bd15cddb | 38 | 7c48f1f2fc790962dea15d81d95bce20b80dae44a9710875888dd63295a21dbc |
| Android / arm64-v8a | exreader-arm64-v8a.aar | bd15cddb | N/A (ZIP) | fd25507dff5fa52aabf60b924aa1c1bae7cc10c0c9fd7726cc8c92913001549e |
| macOS / arm64 | libexreader.dylib | bd15cddb | 2799 | 5597c718986b20640f2144eb11cad7ce3104a6de188eb65cee0a72c850f9685d |
| iOS / arm64-device | libexreader.dylib | bd15cddb | 2799 | 882a23f3a05cc9893062568e6d7df3d3cf03fc567bb4c772c0e4e9574f6b7719 |
| iOS / arm64-simulator | libexreader.dylib | bd15cddb | 2799 | 320f6810c1caee0d8f34891b06b3f99e4b67a238e3e4a73c69982289c72bd151 |
| Linux / x86_64 | libexreader.so | bd15cddb | 2799 | be2e9d6b675d92e3719f8149dfc5cac4552333385a0a3c1394f926765afa1d13 |
| Windows / x86_64 | libexreader.dll | ed252fb6 | 419 | a47e097f013e21a93221bb0abf7cfc6a345e322fe2b29913bd3a1c85186c6b18 |
| Android / x86_64 | libexreader.so | ed252fb6 | 1435 | 59cfb88ea8bf6bfa4f4952115107976a6ae47b003ec3f279efbd535de3365e29 |
| Android / x86_64 | libexreader_jni.so | ed252fb6 | 38 | d226215852b638de52cbb3a43311cc3044925ec36efa94871b2f7cc96fbc056a |
| Android / x86_64 | exreader-x86_64.aar | ed252fb6 | N/A (ZIP) | de50ad7803e43bc6b519a1e0445a878675590d8d720bd7ef143eb695440d36ae |
| Android / x86_64 | libplatform_probe.so | ed252fb6 | 2 | 54b668ecfb797ff4b12166dac362dd5696e7db6b8aa0b4ad53a1d35a08a112e9 |
| Android / x86_64 | platform-probe.apk | ed252fb6 | N/A (ZIP) | e97f6dcee004ac6e3088f1bae8d7d547882d5b7231c9338ec05361f8e4ac5921 |
| Linux / x86_64-current | libexreader.so | ed252fb6 | 2843 | 13e2d00dfbddb9e5de708dd88dabb9ce4328a53b1051050c2c58d708c4dffac2 |

AAR/APK 内每个 .so 的导出数和独立 SHA-256 见 [完整 JSON](../../evidence/platforms2-20261109/artifacts.json)。ARM64 AAR 内为 core **2800** / JNI **38**；x86_64 AAR 内为 core **1435** / JNI **38**；测试 APK 另含 probe **2**。APK 与 AAR 内的 core/JNI 字节和独立 .so 一致。

Windows **419** 个导出均以 `exr_` 开头；Android/Linux 允许额外 vendor 导出。Apple 三份库只验证静态结构与既有契约，不算运行时通过。macOS x86_64、iOS x86_64、聚合 iOS `.a` 与 WASM 没有本轮产物，哈希/导出数为 N/A。
