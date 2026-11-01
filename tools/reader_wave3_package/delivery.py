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
        "## 更新前与旧书库",
        "",
        "1. 停止同步并正常关闭所有正在使用该书库的 EXReader；不要在应用仍运行时复制或替换 SQLite 文件。",
        "2. 更新前保留旧程序包，并备份完整用户数据目录及未包含在其中的原始书籍。程序目录不等于书库目录；若无法确认实际数据位置，先不要覆盖或卸载。",
        "3. 将新包解压到不同的空目录。只有本构建附带的兼容性证据明确支持当前旧版本时，才让它打开旧库；没有列出的旧版本、跨 schema 迁移和降级不视为支持。",
        "4. 首次打开后检查原件、书架、阅读位置、笔记与设置。发生错误时保留错误信息和现有数据，不要用删除数据库或重建空库掩盖问题。",
        "5. 升级前备份恢复与直接把新版本改过的库交给旧版本不同。不要默认后者安全；需要恢复时先退出所有程序，保留失败现场，再按该版本已验证的恢复流程操作。",
        "- 本说明未新增自动备份、自动升级或任意降级功能，也不把独立迁移组件通过解释为本包全平台升级已通过。",
        "",
        "## 导入与本机数据",
        "",
        "- 使用应用当前提供的本地导入入口，先用副本或随包 Sample 检查本目标实际支持的格式；手机/模拟器使用系统文件选择器授予所需文件访问。",
        "- 导入取消或失败后查看应用提示与书架，再决定是否重试；不要假定取消会撤回已经提交的部分。重复导入的结果以该版本实际提示为准，不承诺所有目标自动去重。",
        "- “移除本机下载”与“从书库删除”不是同一操作：前者不应被解释为删除远端书籍，后者可能产生同步删除记录。若当前目标没有清楚的独立入口，不要通过删除数据库或同步目录里的文件模拟操作。",
        "",
        "## 账号同步、取消与冲突",
        "",
        "- 仅使用你有权访问的 HTTPS WebDAV 服务，为 EXReader 指定专用目录；不要把正在使用的 SQLite 数据库文件放进网盘同步来替代应用协议。",
        "- 按应用当前账号界面填写地址和凭据；不要把密码写入日志、问题报告或本说明。遇到证书错误先修复服务证书与信任配置，不关闭 TLS 校验。",
        "- 首次同步先确认账号、目录和网络；传输完成、接收投影完成与书籍已下载可读可能是不同阶段。请按下面的平台说明确认，不以一个进度条结束推定所有端已一致。",
        "- 离线时只使用已在本机可用的内容；重新联网后通过原同步/重试入口继续。取消不会自动撤销已经提交的操作；等待取消或关闭完成，不直接删除临时文件。",
        "- 看到并发修改或删除冲突时保留现有数据并查看原界面提示，不假定自动合并。只有版本明确提供恢复/解决入口时才使用；旧修改重新出现不等于授权恢复已删除书籍。",
        "- 若该目标尚未提供足够的冲突详情或处理入口，请保留记录并报告限制；不要把未验证功能写成已支持。",
        "",
        "## 许可与依赖材料",
        "",
        "- 保留包内 LICENSE、THIRD_PARTY_NOTICES、licenses 及字体许可等随附材料；不同目标的路径和实际依赖可能不同。",
        "- 包内材料应与本 manifest 的构建源和实际程序相符。材料缺失或版本对应不清时先报告，不用仓库中有同名文件替代随包核对，也不把本开发包当作正式发布许可审计结论。",
        "",
        '## 范围与限制',
        '',
    ]
    sync_notes = {
        "windows": "Windows：账号传输完成后该宿主会自动进入接收；查看最终投影/导入及冲突提示，而非只看传输结束。",
        "linux": "GTK：Sync library 扫描与 Receive 接收是不同操作；扫描完成后按当前界面执行 Receive，云书仍需实际打开或下载后才可离线阅读。",
        "android": "Android：按当前同步面板的同步、取消与书籍接收/重试入口操作；这是模拟器开发包，不能据此承诺真机行为或完整删除冲突详情。",
        "macos": "macOS：按当前账号界面的同步/取消入口操作；书籍接收与组织视图能力按本构建实证为准，不承诺打开中的组织面板自动刷新。",
        "iphone": "iPhone：仅本包所列模拟器安装方式；账号同步/取消与组织视图能力按本构建实证为准，不把模拟器通过写成真机或全端组织同步完成。",
        "ipad": "iPad：仅本包所列模拟器安装方式；账号同步/取消与组织视图能力按本构建实证为准，不把模拟器通过写成真机或全端组织同步完成。",
    }
    lines += ['- ' + sync_notes[target], '']
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
