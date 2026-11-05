"""Actions-only installed-module/link evidence for the controlled native writer."""
import argparse,hashlib,json,os,re,subprocess
from pathlib import Path
import identity
p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--stage',type=Path,required=True);p.add_argument('--package',type=Path,required=True);a=p.parse_args()
admitted=identity.guard();stage=a.stage.resolve();build=a.build.resolve()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
linked=(build/'linked-modules.txt').read_text().splitlines();assert len(linked)==4 and all(Path(p).resolve().is_relative_to(stage) for p in linked)
expected={'EXReaderDesktopMetadata':'0.1.0','EXReaderCommands':'0.1.0','EXReaderRevisions':'0.3.0'};versions={}
for name,version in expected.items():
    path=stage/'lib/cmake'/name/(name+'ConfigVersion.cmake');actual=re.search(r'set\(PACKAGE_VERSION\s+"([^"]+)"\)',path.read_text()).group(1);assert actual==version
    versions[name]={'actual':actual,'path':str(path),'sha256':sha(path)}
cache=(build/'CMakeCache.txt').read_text()
for name in expected:
    match=re.search(r'^'+name+r'_DIR:PATH=(.*)$',cache,re.M);assert match and Path(match.group(1)).resolve().is_relative_to(stage)
report=dict(identity.retained.identity(),accepted=True,program_sha256=sha(a.package/'gtk-preview-writer'),source_sha256=sha(Path(__file__).parent/'writer/main.cpp'),installed_versions=versions,linked_files={str(Path(p).relative_to(stage)):sha(p) for p in linked[1:]},stage=str(stage),cache_sha256=sha(build/'CMakeCache.txt'),compile_commands_sha256=sha(build/'compile_commands.json'))
(a.package/'writer-identity.json').write_text(json.dumps(report,indent=2));print('GTK_NATIVE_WRITER_IDENTITY '+json.dumps(report),flush=True)
