"""Prepare test-only copies of the existing actual Android UI runners."""
from pathlib import Path
import os
import re
assert os.environ.get('GITHUB_ACTIONS') == 'true'
p = Path('build/android-page-theme/candidate/host-session/java/org/exreader/host/HostSyncTest.java')
s = p.read_text()
needle = '            if(phase.equals("first")){' 
assert s.count(needle) == 1
s = s.replace(needle, '''            if(phase.equals("interop-send")){
                check("actual_activity_syncs_existing_record_sender",()->{launch();panel();settings(false);click("立即同步");status("本轮同步结束");});
                check("actual_session_closes",()->{click("断开");closed();});
            }else if(phase.equals("first")){''')
p.write_text(s)
p = Path('tests/reader_android_record_interop/run_ui.py')
s = p.read_text()
s, count = re.subn(r",'missing-parent':\[[^\]]*\]", '', s, count=1)
assert count == 1
old = "len({row['pid'] for row in reports})==2 and sum(row['count'] for row in reports)==8"
assert old in s
s = s.replace(old, "len(reports)==1 and sum(row['count'] for row in reports)==6")
Path('build/android-page-theme/candidate/record_sender_only.py').write_text(s)
