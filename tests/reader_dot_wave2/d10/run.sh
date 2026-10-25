#!/usr/bin/env bash
set -euo pipefail
platform="$1"
harness="$PWD"
cd target
mkdir -p build/d10/results build/d10/accessibility/ui
# Reuse the exact original tests and recorder; no editing/retry injection.
cp tests/apple_host/accessibility/ui/ReaderAccessUITests.swift build/d10/accessibility/ui/
cp "$harness/tests/reader_dot_wave2/d10/accessibility/A11yAuditSupport.swift" build/d10/accessibility/ui/
cp "$harness/tests/reader_dot_wave2/d10/accessibility/DefaultUITests.swift" build/d10/accessibility/ui/
python3 tests/apple_host/prepare_fixtures.py --resources build/apple-resources
ruby -e "require 'xcodeproj'" || gem install xcodeproj --no-document
# Owned generator copy derives identity from actual target checkout, never spoofs GitHub identity.
python3 - <<'GEN'
from pathlib import Path
s=Path('tests/apple_host/make_xcodeproj.rb').read_text()
s=s.replace("source_sha = ENV.fetch('GITHUB_SHA')", "source_sha = `git rev-parse HEAD`.strip")
Path('build/d10/make_xcodeproj.rb').write_text(s)
GEN
ruby build/d10/make_xcodeproj.rb build/d10/project build/apple-resources build/d10/accessibility/ui
# The generator's /accessibility/ route excludes all review conditions.
if grep -E 'SWIFT_ACTIVE_COMPILATION_CONDITIONS.*EXR_' build/d10/project/EXReaderHost.xcodeproj/project.pbxproj; then
  echo 'D10 refuses a review-enabled program'; exit 1
fi
python3 - "$platform" > build/d10/destination.txt <<'PY'
import json,subprocess,sys
if sys.argv[1]=='macos': print('platform=macOS\nmacos\nmacOS host\nmacOS');sys.exit()
prefix='iPhone' if sys.argv[1]=='iphone' else 'iPad'
data=json.loads(subprocess.check_output(['xcrun','simctl','list','devices','available','--json']))
runtime,name,udid=max((r,d['name'],d['udid']) for r,ds in data['devices'].items() for d in ds if d.get('isAvailable') and d['name'].startswith(prefix))
print('platform=iOS Simulator,id='+udid+'\n'+udid+'\n'+name+'\n'+runtime)
PY
cat build/d10/destination.txt
udid=$(sed -n '2p' build/d10/destination.txt)
if [ "$platform" = macos ]; then
  scheme=EXReaderHost-macOS; suite=EXReaderHostUITests-macOS; signing=YES
  defaults write -g AppleKeyboardUIMode -int 3
  defaults read -g AppleKeyboardUIMode > build/d10/keyboard-ui-mode.txt
else
  scheme=EXReaderHost-iOS; suite=EXReaderHostUITests-iOS; signing=NO
  xcrun simctl boot "$udid"
  xcrun simctl bootstatus "$udid" -b
  python3 - "$udid" <<'READY'
import sys
from pathlib import Path
sys.path.insert(0,'tests/apple_host/page_theme')
from simulator_ready import prepare_service
prepare_service(sys.argv[1], Path('build/d10'))
READY
  xcrun simctl ui "$udid" content_size medium
  xcrun simctl ui "$udid" content_size > build/d10/normal-content-size.txt
fi
run_case() {
  local label="$1" selector="$2"
  set +e
  xcodebuild test -project build/d10/project/EXReaderHost.xcodeproj -scheme "$scheme" \
    -destination "$(head -1 build/d10/destination.txt)" -derivedDataPath build/d10/DerivedData \
    -resultBundlePath "build/d10/results/$label.xcresult" -parallel-testing-enabled NO \
    -test-timeouts-enabled YES -default-test-execution-time-allowance 420 -maximum-test-execution-time-allowance 900 \
    "-only-testing:$suite/$selector" EXR_SDK_DIR="$PWD/stage" CODE_SIGNING_ALLOWED="$signing" \
    TEST_RUNNER_EXR_A11Y_PLATFORM="$platform" 2>&1 | tee "build/d10/results/$label.log"
  result=${PIPESTATUS[0]}
  set -e
  echo "$result" > "build/d10/results/$label.exit"
}
appearance() {
  python3 - "$platform" "$udid" "$1" <<'APPEARANCE'
import subprocess,sys
platform,udid,value=sys.argv[1:]
if platform=='macos':
    subprocess.run(['osascript','-e','tell application "System Events" to tell appearance preferences to set dark mode to '+str(value=='dark').lower()],check=True,timeout=45)
    result=subprocess.check_output(['osascript','-e','tell application "System Events" to tell appearance preferences to get dark mode'],text=True,timeout=45).strip()
    assert result==str(value=='dark').lower()
else:
    subprocess.run(['xcrun','simctl','ui',udid,'appearance',value],check=True,timeout=45)
    result=subprocess.check_output(['xcrun','simctl','ui',udid,'appearance'],text=True,timeout=45).strip()
    assert result==value
print('D10_APPEARANCE',platform,value,result)
APPEARANCE
}
appearance light
run_case import ReaderAccessUITests/test01ProductionBodyNamesAndActualEdgeTap
for mode in light dark; do
  appearance "$mode"
  if [ "$platform" != macos ]; then xcrun simctl ui "$udid" content_size medium; fi
  run_case "normal-$mode" DefaultUITests
  if [ "$platform" != macos ]; then
    xcrun simctl ui "$udid" content_size accessibility-extra-extra-extra-large
    xcrun simctl ui "$udid" content_size > build/d10/large-content-size.txt
    if [ "$mode" = light ]; then run_case original-large ReaderAccessUITests/test02CompactReaderActualTurnFontAndNotes; fi
    run_case "large-$mode" DefaultUITests
  fi
done
if [ "$platform" = macos ]; then
  run_case original-compact ReaderAccessUITests/test02CompactReaderActualTurnFontAndNotes
  echo 'pending: no platform-supported system large-font setting exercised' > build/d10/large-content-size.txt
fi
