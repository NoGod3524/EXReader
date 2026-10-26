#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Small Actions-only contract check for the real Android Gradle hand-off."""
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/reader_wave3_package'))
import mobile


def main():
    mobile.actions_only()
    with tempfile.TemporaryDirectory() as folder:
        build = Path(folder)
        sdk, product = build / 'sdk', build / 'product'
        events = []
        def install(*arguments):
            assert arguments == (sdk, product, build / 'features')
            events.append('installed')
        def run(arguments, **options):
            events.append(arguments)
            return mock.Mock(returncode=0)
        with mock.patch.object(mobile, 'install_android_features', side_effect=install), \
             mock.patch.object(mobile.subprocess, 'run', side_effect=run):
            assert mobile.gradle_android(sdk, product, build, '/real/gradle', ['--version']) == 0
            assert events == [['/real/gradle', '--version']]
            assert not (build / 'mobile-profile.json').exists()
            events.clear()
            original = ['-p', 'examples/android', '--no-daemon', ':app:assembleDebug', '-PexrSdk=' + str(sdk)]
            assert mobile.gradle_android(sdk, product, build, '/real/gradle', original) == 0
            assert events[0] == 'installed'
            argv = events[1]
            assert argv[:len(original) + 1] == ['/real/gradle', *original]
            for feature in ('Search', 'Navigation', 'Reading', 'Preferences'):
                assert '-Pexr' + feature + '=true' in argv
            assert '-PexrProduct=' + str(product) in argv
            assert '-PexrSearchPrefix=' + str(product) in argv
            assert '-PexrNavigationPrefix=' + str(product) in argv
            assert '-PexrPreferencesPrefix=' + str(product) in argv
            profile = json.loads((build / 'mobile-profile.json').read_text())
            assert all(profile['features'].values())
            assert profile['sdk_version'] == '3.41.0'
            assert not profile['physical_device_execution']
            assert profile['source_sha'] == os.environ['GITHUB_SHA']
        with mock.patch.object(mobile.subprocess, 'run', return_value=mock.Mock(returncode=23)):
            assert mobile.gradle_android(sdk, product, build, '/real/gradle', ['--version']) == 23
    print('Android delivery profile keeps original Gradle tasks, enables all four features and propagates failures')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
