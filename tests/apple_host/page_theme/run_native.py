# SPDX-License-Identifier: MIT
"""Compile OFF/ON consumers of the one installed SDK and compare real pixels."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    parser = argparse.ArgumentParser()
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--resources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[3]
    sdk, resources, out = args.sdk.absolute(), args.resources.absolute(), args.output.absolute()
    out.mkdir(parents=True, exist_ok=True)

    def run(command, name, *, environment=None, failure=None):
        with (out / name).open('wb') as log:
            result = subprocess.run([str(v) for v in command], cwd=repo, env=environment,
                                    stdout=log, stderr=subprocess.STDOUT, timeout=1200)
        content = (out / name).read_text(errors='replace')
        print(content, flush=True)
        if failure is None:
            assert result.returncode == 0, name
        else:
            assert result.returncode != 0 and failure in content, 'inactive/reasonless rejection: ' + name
        return content

    for tool in ('prepare_fixtures.py', 'navigation/prepare_navigation_fixture.py', 'reading/prepare_reading_fixture.py',
                 'page_theme/prepare_fixtures.py'):
        run([sys.executable, 'tests/apple_host/' + tool, '--resources', resources], tool.replace('/', '-') + '.log')
    clean_env = {k: v for k, v in os.environ.items() if k not in ('EXR_APPLE_SDK_VERSION', 'EXR_APPLE_PAGE_THEME')}
    for tool, extra in [('tools/build_apple_product.py', ['--target', 'macos', '--build', out / 'should-not-build']),
                        ('tools/build_apple_host.py', ['--platform', 'macos', '--output', out / 'should-not-exist'])]:
        run([sys.executable, tool, '--sdk', sdk, *extra], Path(tool).stem + '-default-reject.log',
            environment=clean_env, failure='Installed SDK version differs')
        run([sys.executable, tool, '--sdk', sdk, '--sdk-version', '3.40.0', *extra], Path(tool).stem + '-mixed-reject.log',
            environment=clean_env, failure='Installed SDK version differs')
    run([sys.executable, 'tools/build_apple_host.py', '--sdk', sdk, '--sdk-version', '3.40.0', '--page-theme',
         '--platform', 'macos', '--output', out / 'should-not-exist'], 'theme-340-reject.log',
        environment=clean_env, failure='--page-theme requires explicit --sdk-version=3.41.0')
    assert not (out / 'should-not-exist').exists() and not (out / 'should-not-build').exists()
    books = ('Theme.txt', 'ThemeText.epub', 'ThemeAuthored.epub', 'Sample.pdf', 'NavigationPages.cbz')
    originals, reports, binaries = {}, {}, {}
    for mode in ('off', 'on'):
        program = out / ('theme-review-' + mode)
        command = [sys.executable, 'tools/apple_swift.py', '--sdk', sdk, '--', '-swift-version', '5',
                   '-parse-as-library', '-O', '-D', 'EXR_APPLE_HOST_REVIEW']
        if mode == 'on':
            command += ['-D', 'EXR_APPLE_PAGE_THEME']
        command += ['-I', sdk / 'include', '-L', sdk / 'lib', '-lexreader', '-Xlinker', '-rpath', '-Xlinker', sdk / 'lib',
                    'examples/apple/HostSDK.swift', 'examples/apple/HostModel.swift', 'examples/apple/HostCatalog.swift',
                    'examples/apple/SelectableText.swift', 'tests/apple_host/page_theme/ThemeReview.swift', '-o', program]
        run(command, 'build-' + mode + '.log')
        run([program, resources, out / mode], 'consumer-' + mode + '.log')
        symbols = run(['nm', '-g', program], 'symbols-' + mode + '.txt')
        imported = len(re.findall(r'\bU\s+_exr_render_page_background\s*$', symbols, re.M))
        assert imported == (1 if mode == 'on' else 0), 'new SDK API leaked into disabled host or missing in enabled host'
        assert not re.search(r'\b[Tt]\s+_exr_render_page', symbols), 'embedded SDK renderer'
        provider = json.loads(Path(str(program) + '.product.json').read_text())
        assert provider['accepted'] is True and provider['static_sdk_linked'] is False
        report = json.loads((out / mode / 'theme-review.json').read_text())
        assert report['accepted'] is True and report['theme_enabled'] == (mode == 'on')
        assert report['sdk'] == '3.41.0' and report['abi'] == 1
        assert all(report[key] == os.environ[env] for key, env in
                   [('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT')])
        expected = {book + ':' + suffix for book in books for suffix in ('original', 'source-retained')}
        if mode == 'on':
            expected |= {book + ':' + suffix for book in books for suffix in ('dark', 'light', 'system', 'original-roundtrip')}
            expected |= {book + ':' + suffix for book in books[:2] for suffix in ('cancel-every-sdk-poll', 'post-render-failure')}
        names = [row['id'] for row in report['checks']]
        assert set(names) == expected and all(row['passed'] is True for row in report['checks'])
        assert len(names) == len(set(names)), 'duplicate native check identity'
        originals[mode] = {book: (out / mode / (book + '.original.rgba')).read_bytes() for book in books}
        reports[mode] = report
        binaries[mode] = {'sha256': hashlib.sha256(program.read_bytes()).hexdigest(), 'new_api_imports': imported, 'provider': provider}
    assert originals['on'] == originals['off'], 'flag ON initial original pixels differ from OFF'
    result = {'accepted': True, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'sdk_version': '3.41.0', 'sdk_abi': 1,
              'sdk_source': 'edddc463c06ed5731195cdb8f06b2df6dff7699e', 'reports': reports, 'binaries': binaries,
              'original_on_off_exact': True, 'mixed_version_rejections': 5, 'complete_product': False,
              'old_340_migration_tested': False}
    (out / 'native.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print('PAGE_THEME_NATIVE_VERIFIED')


if __name__ == '__main__':
    main()
