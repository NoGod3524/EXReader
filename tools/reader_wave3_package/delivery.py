# SPDX-License-Identifier: MIT
"""Shared contract for the S20 six-target native delivery archives.

One archive per target holds the real build payload produced by the existing
platform build scripts, the checksum list, the short Chinese operator notes and
a machine readable manifest. Nothing here builds or judges the product: the
platform build scripts and the platform UI drivers stay the only authorities.
"""
import hashlib
import json
import re
from pathlib import Path

SCHEMA = 1
MANIFEST = 'manifest.json'
CHECKSUMS = 'SHA256SUMS'
INSTRUCTIONS = '\u5b89\u88c5\u8bf4\u660e-\u4e2d\u6587.md'
SOURCE_PATTERN = re.compile(r'\A[0-9a-f]{40}\Z')

TARGETS = {
    'windows': {
        'label': 'Windows x86_64',
        'entry': 'EXReader/EXReader.exe',
        'launch': '解压后运行 EXReader\\EXReader.exe（Windows 10/11 x64，无安装程序）。',
        'limits': [
            '未做代码签名与公证，首次运行可能出现 SmartScreen 提示。',
            '仅提供 x64 解压即用包，不包含安装器、注册表写入或开机自启。',
        ],
    },
    'linux': {
        'label': 'Linux x86_64 (GTK3)',
        'entry': 'EXReader-Linux/bin/exreader-linux',
        'launch': '解压后运行 EXReader-Linux/Start-EXReader.sh（需 GTK3）；书库和状态默认保存在当前用户数据目录。',
        'limits': [
            '未打包为 deb/rpm；系统需自带 GTK3 与基础 X11 库。',
            '只在 ubuntu-22.04 上构建与验证，其他发行版未声称。',
        ],
    },
    'macos': {
        'label': 'macOS 12+ (arm64)',
        'entry': 'EXReader.app/Contents/MacOS/EXReader',
        'launch': '解压后双击 EXReader.app，或执行 open EXReader.app。',
        'limits': [
            '仅 ad-hoc 签名，未做开发者 ID 签名与公证；Gatekeeper 可能要求手动放行。',
            '仅在 macOS 15 构建机上验证。',
        ],
    },
    'android': {
        'label': 'Android x86_64 模拟器 (API 34)',
        'entry': 'artifacts/app-debug.apk',
        'launch': 'adb install -r artifacts/app-debug.apk，然后启动 org.exreader.host。',
        'limits': [
            '只授予 x86_64 API 34 模拟器；未验证真机、arm64 或其他 API。',
            'APK 为 debug 签名，不适合商店上架。',
        ],
    },
    'iphone': {
        'label': 'iPhone 模拟器 (iOS 15+)',
        'entry': 'EXReader.app/EXReader',
        'launch': 'xcrun simctl install <udid> EXReader.app，然后 xcrun simctl launch <udid> org.exreader.host。',
        'limits': [
            '只授予苹果模拟器；未签名的 .app 不能安装到真机。',
            '仅支持 arm64 模拟器，且未做 App Store 提交。',
        ],
    },
    'ipad': {
        'label': 'iPad 模拟器 (iOS 15+)',
        'entry': 'EXReader.app/EXReader',
        'launch': 'xcrun simctl install <udid> EXReader.app，然后 xcrun simctl launch <udid> org.exreader.host。',
        'limits': [
            '只授予苹果模拟器；未签名的 .app 不能安装到真机。',
            '仅支持 arm64 模拟器，且未做 App Store 提交。',
        ],
    },
}


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def sha256_file_bytes(data):
    return hashlib.sha256(data).hexdigest()


def normalise(relative):
    return str(relative).replace('\\', '/')


def collect(root, excludes=()):
    """Return sorted payload records; symlinks become their target bytes."""
    root = Path(root)
    patterns = tuple(excludes)
    records = {}
    for path in sorted(root.rglob('*')):
        relative = normalise(path.relative_to(root))
        if not relative or path.is_dir():
            continue
        if any(relative == item or relative.startswith(item.rstrip('/') + '/') for item in patterns):
            continue
        if path.is_symlink() and not path.resolve().is_file():
            raise SystemExit('refusing a symlink that does not resolve to a file: ' + relative)
        mode = 0o755 if (path.stat().st_mode & 0o111) else 0o644
        records[relative] = {'bytes': path.stat().st_size, 'sha256': sha256_file(path), 'mode': mode}
    if not records:
        raise SystemExit('payload directory is empty: ' + str(root))
    return records


def instructions(target, source_sha, sdk_version):
    spec = TARGETS[target]
    lines = [
        '# EXReader ' + spec['label'] + ' 下载包说明',
        '',
        '- 构建源：' + source_sha,
        '- 阅读 SDK：' + sdk_version,
        '- 包内含整个构建产出目录、SHA256SUMS 与 manifest.json。',
        '',
        '## 怎么运行',
        '',
        '1. 解压到任意空目录。',
        '2. ' + spec['launch'],
        '3. 首次打开时用自带的 Sample 书试读：本地导入 → 打开 → 翻页 → 设置 → 搜索/目录。',
        '',
        '## 校验',
        '',
        '在解压目录内执行：',
        '',
        '- Linux / macOS：`sha256sum -c SHA256SUMS`',
        '- Windows：`certutil -hashfile <文件> SHA256` 逐个比对 SHA256SUMS',
        '- manifest.json 逐文件记录字节数与 SHA-256，并带构建源与 run/attempt。',
        '',
        '## 范围与限制',
        '',
    ]
    lines += ['- ' + item for item in spec['limits']]
    lines += [
        '- 本包不包含 tag / Release / 商店发布，也不声称完整产品。',
        '',
    ]
    return '\n'.join(lines)


def checksums(records):
    return ''.join(record['sha256'] + '  ' + name + '\n' for name, record in sorted(records.items()))


def manifest(target, source_sha, sdk_version, records, excludes, archive_name):
    spec = TARGETS[target]
    return {
        'schema': SCHEMA,
        'kind': 'exreader-native-delivery',
        'target': target,
        'label': spec['label'],
        'source_sha': source_sha,
        'sdk_version': sdk_version,
        'entry': spec['entry'],
        'archive_name': archive_name,
        'excluded': list(excludes),
        'files': records,
        'limits': spec['limits'],
        'instructions': INSTRUCTIONS,
        'checksums': CHECKSUMS,
    }
