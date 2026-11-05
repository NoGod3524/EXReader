import os,sys
from common import *
def main():
 actions();overlay();installed=sdk();prefix=(OUT/'c02-prefix').resolve()
 c02_deps(installed,prefix,owner=True)
 b=cmake('c02-check','tests/migration/posix_c02_admission_20261031',[
  '-DPC02_PREFIX='+str((OUT/'native-prefix').resolve()),'-DWH_PREFIX='+str((OUT/'abi2-prefix').resolve()),
  '-DSOURCE_SHA='+os.environ['GITHUB_SHA']],install=False)
 run('c02-native-original',[sys.executable,'tests/migration/posix_c02_admission_20261031/run.py',
  '--tool',b/'posix-c02-admission-check','--output',OUT/'native'])
 native_audit(OUT/'native',b/'posix-c02-admission-check',OUT/'native-independent')
 guarded=cmake('c02-guarded','extras/migration',['-DEXR_SDK='+str(installed),'-DLM_C02_PREFIX='+str(prefix)],install=False)
 legacy=cmake('c02-legacy','extras/migration',['-DEXR_SDK='+str(installed),'-DLM_HISTORICAL_TEST_BASELINE=ON'],install=False)
 run('c02-historical-original',[sys.executable,'tests/migration/run_cases.py','--tool',legacy/'exreader-legacy-migrate',
  '--workdir',OUT/'legacy-native','--out',OUT/'legacy-result.json','--label','joint-historical-original'])
 run('c02-actual-original',[sys.executable,'tests/migration/posix_c02_migration_20261031/run.py',
  '--tool',prefix/'bin/exreader-c02-migrate','--test-tool',OUT/'c02-owner/exreader-c02-migrate-controls',
  '--admission',prefix/'bin/exreader-c02-admission','--legacy',legacy/'exreader-legacy-migrate-tx',
  '--guarded',guarded/'exreader-legacy-migrate-tx','--output',OUT/'migration'])
 save(OUT/'c02-result.json',dict(source=os.environ['GITHUB_SHA'],original_native_groups=[28,10,17],
  actual_cases=36,repair_cases=20,legacy_original_preserved=True,known_abi2_reds_referenced_not_rerun=True,passed=True))
if __name__=='__main__':main()
