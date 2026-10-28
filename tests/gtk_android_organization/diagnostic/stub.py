"""Build test instrumentation only. Stub host is NEVER installed/executed."""
import os
from pathlib import Path
assert os.environ.get('GITHUB_ACTIONS')=='true'
p=Path('examples/android/app/build.gradle');s=p.read_text()
# Remove both native build DSL blocks from compile-only Java host target.
while 'externalNativeBuild {' in s:
 start=s.index('externalNativeBuild {');at=s.index('{',start);depth=1;end=at+1
 while depth:
  if s[end]=='{':depth+=1
  elif s[end]=='}':depth-=1
  end+=1
 s=s[:start]+s[end:]
s+='\nandroid.sourceSets.androidTest.java.setSrcDirs([file("../../../tests/gtk_android_organization/android/java")])\n'
s+='android.sourceSets.androidTest.manifest.srcFile file("../../../tests/gtk_android_organization/diagnostic/AndroidManifest.xml")\n'
p.write_text(s)
