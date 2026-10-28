"""Build only the focused Windows font acceptance host in Actions."""
import os
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/reader_windows_raw3'))
sys.path.insert(0, str(ROOT / 'tests/reader_wave3_c09'))
import host_build as H
import build as C

assert os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'win32'
out = ROOT / 'build/windows-font'
out.mkdir(parents=True, exist_ok=False)
(out / 'logs').mkdir()
H.OUT = out
sdk, product, stage = out / 'sdk-stage', out / 'product-stage', out / 'raw-stage'
prefix = ';'.join(map(str, (stage, product, sdk)))
H.run(['cmake', '--preset', 'reading-library', '-B', out / 'sdk-build', '-DCMAKE_INSTALL_PREFIX=' + str(sdk)], 'sdk-configure')
H.run(['cmake', '--build', out / 'sdk-build', '--parallel', '4'], 'sdk-build')
H.run(['cmake', '--install', out / 'sdk-build'], 'sdk-install')
H.configure(ROOT / 'apps/reader/store/native', out / 'product-build', ['-DCMAKE_INSTALL_PREFIX=' + str(product)], 'product')
H.run(['cmake', '--install', out / 'product-build'], 'product-install')
for module in tuple(H.MODULES) + C.NEW_MODULES:
    label = Path(module).name
    options = ['-DCMAKE_INSTALL_PREFIX=' + str(stage), '-DCMAKE_PREFIX_PATH=' + prefix, '-DEXR_SDK=' + str(sdk),
               '-DEXR_SDK_VERSION=3.41.0', '-DREADER_PRODUCT_PREFIX=' + str(product)] + C.EXTRA_FLAGS.get(label, [])
    if label == 'cloud-import':
        options.append('-DREADER_CLOUD_BUILD_CONTENT_BOUND=ON')
    if label in set(H.RAW_MODULES) | C.RAW_NEW:
        options.append('-DEXR_READER_SELECTOR_BYTES_CANDIDATE=ON')
    build = out / ('raw-' + label)
    H.configure(ROOT / module, build, options, 'raw-' + label)
    H.run(['cmake', '--install', build], 'raw-' + label + '-install')
H.run(['cmake', '-S', ROOT / 'apps/reader/desktop', '-B', out / 'host', '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
       '-DCMAKE_PREFIX_PATH=' + prefix, '-DEXR_SDK=' + str(sdk), '-DEXR_SDK_VERSION=3.41.0',
       '-DREADER_METADATA_PREFIX=' + str(stage), '-DREADER_ACCOUNT_PREFIX=' + str(stage),
       '-DEXR_READER_WINDOWS_WAVE3=ON', '-DEXR_READER_WINDOWS_CLOUD_CONTENT_BOUND=ON',
       '-DEXR_WINDOWS_FONT_REVIEW=ON'], 'host-configure')
H.run(['cmake', '--build', out / 'host', '--target', 'EXReaderWave3', '--parallel', '4'], 'host-build')
