#!/usr/bin/env bash
set -euo pipefail
platform="$1"
mkdir -p build/d04/results build/d04/accessibility
# Reuse the exact original tests and recorder; no editing/retry injection.
cp tests/apple_host/accessibility/ui/ReaderAccessUITests.swift build/d04/accessibility/
cp tests/reader_a11y_apple/A11yAuditSupport.swift build/d04/accessibility/
cp tests/reader_final_d04/accessibility/DefaultUITests.swift build/d04/accessibility/
python3 tests/apple_host/prepare_fixtures.py --resources build/apple-resources
ruby -e "require 'xcodeproj'" || gem install xcodeproj --no-document
GITHUB_SHA="$TARGET_SHA" ruby tests/apple_host/make_xcodeproj.rb build/d04/project build/apple-resources build/d04/accessibility/
# The generator's /accessibility/ route excludes all review conditions.
! grep -E 'SWIFT_ACTIVE_COMPILATION_CONDITIONS.*EXR_' build/d04/project/EXReaderHost.xcodeproj/project.pbxproj
python3 - "$platform" > build/d04/destination.txt <<'PY'
import json,subprocess,sys
if sys.argv[1]=='macos': print('platform=macOS\nmacos\nmacOS host\nmacOS');sys.exit()
prefix='iPhone' if sys.argv[1]=='iphone' else 'iPad'
data=json.loads(subprocess.check_output(['xcrun','simctl','list','devices','available','--json']))
runtime,name,udid=max((r,d['name'],d['udid']) for r,ds in data['devices'].items() for d in ds if d.get('isAvailable') and d['name'].startswith(prefix))
print('platform=iOS Simulator,id='+udid+'\n'+udid+'\n'+name+'\n'+runtime)
PY
cat build/d04/destination.txt
udid=$(sed -n '2p' build/d04/destination.txt)
if [ "$platform" = macos ]; then
  scheme=EXReaderHost-macOS; suite=EXReaderHostUITests-macOS; signing=YES
  defaults write -g AppleKeyboardUIMode -int 3
  defaults read -g AppleKeyboardUIMode > build/d04/keyboard-ui-mode.txt
else
  scheme=EXReaderHost-iOS; suite=EXReaderHostUITests-iOS; signing=NO
  xcrun simctl boot "$udid"
  xcrun simctl bootstatus "$udid" -b
  xcrun simctl ui "$udid" content_size medium
  xcrun simctl ui "$udid" content_size > build/d04/normal-content-size.txt
fi
run_case() {
  local label="$1" selector="$2"
  set +e
  xcodebuild test -project build/d04/project/EXReaderHost.xcodeproj -scheme "$scheme" \
    -destination "$(head -1 build/d04/destination.txt)" -derivedDataPath build/d04/DerivedData \
    -resultBundlePath "build/d04/results/$label.xcresult" -parallel-testing-enabled NO \
    -test-timeouts-enabled YES -default-test-execution-time-allowance 420 -maximum-test-execution-time-allowance 900 \
    "-only-testing:$suite/$selector" EXR_SDK_DIR="$PWD/stage" CODE_SIGNING_ALLOWED="$signing" \
    TEST_RUNNER_EXR_A11Y_PLATFORM="$platform" 2>&1 | tee "build/d04/results/$label.log"
  result=${PIPESTATUS[0]}
  set -e
  echo "$result" > "build/d04/results/$label.exit"
}
run_case import ReaderAccessUITests/test01ProductionBodyNamesAndActualEdgeTap
run_case normal DefaultUITests
if [ "$platform" != macos ]; then
  xcrun simctl ui "$udid" content_size accessibility-extra-extra-extra-large
  xcrun simctl ui "$udid" content_size > build/d04/large-content-size.txt
  run_case original-large ReaderAccessUITests/test02CompactReaderActualTurnFontAndNotes
  run_case large DefaultUITests
else
  run_case original-compact ReaderAccessUITests/test02CompactReaderActualTurnFontAndNotes
  echo 'pending: no platform-supported system large-font setting exercised' > build/d04/large-content-size.txt
fi
