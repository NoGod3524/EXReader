"""Actions-only reuse of real host UI helpers, with public single-owner seeding/state."""
import os
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS') == 'true'
source=Path('tests/reader_android_preferences/java/org/exreader/host/PreferencesUiTest.java').read_text()
source=source[:source.index('    private JSONObject colorFailure;')]
source=source.replace('public final class PreferencesUiTest','public final class RecordInteropTest')
start=source.index('    private void seed()throws Exception')
end=source.index('    private JSONObject tree(',start)
source=source[:start]+Path('tests/reader_android_record_interop/public_state.java.inc').read_text()+'\n'+source[end:]
source+='\n'+Path('tests/reader_android_record_interop/record_cases.java.inc').read_text()+'\n}\n'
folder=Path('build/android-page-theme/candidate/preferences/java/org/exreader/host');folder.mkdir(parents=True,exist_ok=True)
(folder/'RecordInteropTest.java').write_text(source)
