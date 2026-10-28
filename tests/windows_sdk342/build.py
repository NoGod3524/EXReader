"""Build the Windows Wave3 host against SDK 3.42 in GitHub Actions."""
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/reader_windows_raw3'))
import host_build as H
sys.path.insert(0, str(ROOT / 'tests/reader_wave3_c09'))
from build import NEW_MODULES, RAW_NEW, EXTRA_FLAGS

if os.environ.get('GITHUB_ACTIONS') != 'true' or sys.platform != 'win32':
    raise RuntimeError('Windows Actions only')
out = ROOT / 'build/windows-sdk342'
out.mkdir(parents=True, exist_ok=False)
(out / 'logs').mkdir()
H.OUT = out
sdk, product, stage = out / 'sdk', out / 'product', out / 'raw'
prefix = ';'.join(map(str, (stage, product, sdk)))
H.run(['cmake', '--preset', 'reading-library', '-B', out / 'sdk-build',
       '-DCMAKE_INSTALL_PREFIX=' + str(sdk)], 'sdk-configure')
H.run(['cmake', '--build', out / 'sdk-build', '--parallel', '4'], 'sdk-build')
H.run(['cmake', '--install', out / 'sdk-build'], 'sdk-install')
H.configure(ROOT / 'apps/reader/store/native', out / 'product-build',
            ['-DCMAKE_INSTALL_PREFIX=' + str(product)], 'product')
H.run(['cmake', '--install', out / 'product-build'], 'product-install')
for module in tuple(H.MODULES) + NEW_MODULES:
    label = Path(module).name
    options = ['-DCMAKE_INSTALL_PREFIX=' + str(stage), '-DCMAKE_PREFIX_PATH=' + prefix,
               '-DEXR_SDK=' + str(sdk), '-DEXR_SDK_VERSION=3.42.0',
               '-DREADER_PRODUCT_PREFIX=' + str(product)] + EXTRA_FLAGS.get(label, [])
    if label == 'cloud-import':
        options.append('-DREADER_CLOUD_BUILD_CONTENT_BOUND=ON')
    if label in set(H.RAW_MODULES) | RAW_NEW:
        options.append('-DEXR_READER_SELECTOR_BYTES_CANDIDATE=ON')
    build = out / ('module-' + label)
    H.configure(ROOT / module, build, options, 'module-' + label)
    H.run(['cmake', '--install', build], 'module-' + label + '-install')
host = out / 'host'
H.run(['cmake', '-S', ROOT / 'apps/reader/desktop', '-B', host, '-G', 'Ninja',
       '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_PREFIX_PATH=' + prefix,
       '-DEXR_SDK=' + str(sdk), '-DEXR_SDK_VERSION=3.42.0',
       '-DREADER_METADATA_PREFIX=' + str(stage), '-DREADER_ACCOUNT_PREFIX=' + str(stage),
       '-DEXR_READER_WINDOWS_WAVE3=ON', '-DEXR_READER_WINDOWS_CLOUD_CONTENT_BOUND=ON',
       '-DEXR_READER_WINDOWS_TXT_PROGRESS=ON'], 'host-configure')
H.run(['cmake', '--build', host, '--target', 'EXReaderWave3', '--parallel', '4', '--verbose'], 'host-build')
link_map = (host / 'windows-host.map').read_text(encoding='utf-8', errors='replace')
if not re.search(r'\bexr_webdav_download_observed\b', link_map):
    raise RuntimeError('content-bound transfer missing from link map')
H.run([sys.executable, ROOT / 'tools/build_windows_host.py', '--sdk', sdk,
       '--binary', host / 'EXReaderWave3.exe', '--output', out / 'package',
       '--static-reading'], 'package')
H.configure(ROOT / 'tests/reader_txt_progress/consumer', out / 'txt-consumer',
            ['-DCMAKE_PREFIX_PATH=' + prefix], 'txt-consumer')
H.run([sys.executable, ROOT / 'tests/reader_windows_preferences/make_fixtures.py',
       '--output', out / 'fixtures'], 'fixtures')
H.run([sys.executable, '-c', "from tools.host_font import fetch; fetch('build/host-font-cache')"], 'font')
