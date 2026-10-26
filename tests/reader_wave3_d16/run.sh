#!/usr/bin/env bash
set -euo pipefail
platform="$1"
harness="$PWD"
cd target
mkdir -p build/d16/results build/d16/accessibility/ui
# Reuse exact original tests; independently versioned D16 recorder.
cp tests/apple_host/accessibility/ui/ReaderAccessUITests.swift build/d16/accessibility/ui/
cp "$harness/tests/reader_wave3_d16/accessibility/A11yAuditSupport.swift" build/d16/accessibility/ui/
cp "$harness/tests/reader_wave3_d16/accessibility/DefaultUITests.swift" build/d16/accessibility/ui/
python3 tests/apple_host/prepare_fixtures.py --resources build/apple-resources
ruby -e "require 'xcodeproj'" || gem install xcodeproj --no-document
# Owned generator copy derives identity from actual target checkout, never spoofs GitHub identity.
python3 - <<'GEN'
from pathlib import Path
s=Path('tests/apple_host/make_xcodeproj.rb').read_text()
s=s.replace("source_sha = ENV.fetch('GITHUB_SHA')", "source_sha = `git rev-parse HEAD`.strip")
Path('build/d16/make_xcodeproj.rb').write_text(s)
GEN
ruby build/d16/make_xcodeproj.rb build/d16/project build/apple-resources build/d16/accessibility/ui
# The generator's /accessibility/ route excludes all review conditions.
if grep -E 'SWIFT_ACTIVE_COMPILATION_CONDITIONS.*EXR_' build/d16/project/EXReaderHost.xcodeproj/project.pbxproj; then
  echo 'D16 refuses a review-enabled program'; exit 1
fi
python3 - "$platform" > build/d16/destination.txt <<'PY'
import json,subprocess,sys
if sys.argv[1]=='macos': print('platform=macOS\nmacos\nmacOS host\nmacOS');sys.exit()
prefix='iPhone' if sys.argv[1]=='iphone' else 'iPad'
data=json.loads(subprocess.check_output(['xcrun','simctl','list','devices','available','--json']))
runtime,name,udid=max((r,d['name'],d['udid']) for r,ds in data['devices'].items() for d in ds if d.get('isAvailable') and d['name'].startswith(prefix))
print('platform=iOS Simulator,id='+udid+'\n'+udid+'\n'+name+'\n'+runtime)
PY
cat build/d16/destination.txt
udid=$(sed -n '2p' build/d16/destination.txt)
if [ "$platform" = macos ]; then
  scheme=EXReaderHost-macOS; suite=EXReaderHostUITests-macOS; signing=YES
  defaults write -g AppleKeyboardUIMode -int 3
  defaults read -g AppleKeyboardUIMode > build/d16/keyboard-ui-mode.txt
else
  scheme=EXReaderHost-iOS; suite=EXReaderHostUITests-iOS; signing=NO
  # Same clean ephemeral-device lifecycle as original page_theme/run_ui.py.
  python3 - "$udid" <<'CLEAN'
import subprocess,sys,json
from pathlib import Path
rows=[]
for verb,budget,check in [('shutdown',45,False),('erase',45,True),('boot',45,True),('bootstatus',180,True)]:
    argv=['xcrun','simctl',verb,sys.argv[1]]+(['-b'] if verb=='bootstatus' else [])
    row={'argv':argv,'timeout_seconds':budget}
    try:
        p=subprocess.run(argv,capture_output=True,text=True,timeout=budget)
        row.update(exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr)
    except subprocess.TimeoutExpired:
        row.update(exit_code=None,timed_out=True)
        rows.append(row);Path('build/d16/clean-startup.json').write_text(json.dumps(rows,indent=2));raise
    rows.append(row);Path('build/d16/clean-startup.json').write_text(json.dumps(rows,indent=2))
    if check: assert p.returncode==0,verb+' failed'
CLEAN
  python3 - "$udid" <<'READY'
import sys
from pathlib import Path
sys.path.insert(0,'tests/apple_host/page_theme')
from simulator_ready import prepare_service
prepare_service(sys.argv[1], Path('build/d16'))
READY
  xcrun simctl ui "$udid" content_size medium
  xcrun simctl ui "$udid" content_size > build/d16/normal-content-size.txt
fi
run_case() {
  local label="$1" selector="$2"
  python3 "$harness/tests/reader_wave3_d16/process_watch.py" "build/d16/results/$label-processes.jsonl" &
  watcher=$!
  set +e
  xcodebuild test -project build/d16/project/EXReaderHost.xcodeproj -scheme "$scheme" \
    -destination "$(head -1 build/d16/destination.txt)" -derivedDataPath build/d16/DerivedData \
    -resultBundlePath "build/d16/results/$label.xcresult" -parallel-testing-enabled NO \
    -test-timeouts-enabled YES -default-test-execution-time-allowance 420 -maximum-test-execution-time-allowance 900 \
    "-only-testing:$suite/$selector" EXR_SDK_DIR="$PWD/stage" CODE_SIGNING_ALLOWED="$signing" \
    TEST_RUNNER_EXR_A11Y_PLATFORM="$platform" 2>&1 | tee "build/d16/results/$label.log"
  result=${PIPESTATUS[0]}
  kill "$watcher" 2>/dev/null || true
  wait "$watcher" 2>/dev/null || true
  set -e
  echo "$result" > "build/d16/results/$label.exit"
}
appearance() {
  python3 - "$platform" "$udid" "$1" <<'APPEARANCE'
import subprocess,sys,json
from pathlib import Path
platform,udid,value=sys.argv[1:]
if platform=='macos':
    subprocess.run(['osascript','-e','tell application "System Events" to tell appearance preferences to set dark mode to '+str(value=='dark').lower()],check=True,timeout=45)
    result=subprocess.check_output(['osascript','-e','tell application "System Events" to tell appearance preferences to get dark mode'],text=True,timeout=45).strip()
    assert result==str(value=='dark').lower()
else:
    subprocess.run(['xcrun','simctl','ui',udid,'appearance',value],check=True,timeout=45)
    result=subprocess.check_output(['xcrun','simctl','ui',udid,'appearance'],text=True,timeout=45).strip()
    assert result==value
row=dict(platform=platform,requested=value,observed=result)
with Path('build/d16/appearance.jsonl').open('a') as out: out.write(json.dumps(row)+'\n')
print('D16_APPEARANCE',platform,value,result)
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
    xcrun simctl ui "$udid" content_size > build/d16/large-content-size.txt
    if [ "$mode" = light ]; then run_case original-large ReaderAccessUITests/test02CompactReaderActualTurnFontAndNotes; fi
    run_case "large-$mode" DefaultUITests
  fi
done
if [ "$platform" = macos ]; then
  run_case original-compact ReaderAccessUITests/test02CompactReaderActualTurnFontAndNotes
  echo 'pending: no platform-supported system large-font setting exercised' > build/d16/large-content-size.txt
fi
