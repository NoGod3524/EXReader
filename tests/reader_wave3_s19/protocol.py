"""Exact platform input and installed SDK image identities; no build or acceptance here."""
import hashlib
from pathlib import Path
import re


def require(value,message):
    if not value:raise ValueError(message)


def sdk_aliases(platform,version='3.41.0',abi=1):
    if platform=='Windows':return ('exreader.dll',)
    if platform=='macOS':return ('libexreader.dylib',f'libexreader.{abi}.dylib',f'libexreader.{version}.dylib')
    if platform=='Linux':return ('libexreader.so',f'libexreader.so.{abi}',f'libexreader.so.{version}')
    raise ValueError('Unknown SDK platform: '+platform)


def looks_like_sdk(name):
    name=Path(name).name.lower()
    return (name.startswith('libexreader') and ('.so' in name or name.endswith('.dylib'))) or \
           (name.startswith('exreader') and name.endswith('.dll'))


def installed_sdk(prefix,platform,version='3.41.0'):
    root=Path(prefix).resolve();files=[]
    for name in sdk_aliases(platform,version):
        for folder in ('bin','lib'):
            value=root/folder/name
            if value.is_file():
                require(value.resolve().is_relative_to(root),'SDK image escapes installed prefix')
                files.append(value)
    require(files,'Installed SDK image missing')
    digests={hashlib.sha256(value.read_bytes()).hexdigest() for value in files}
    require(len(digests)==1,'Installed SDK aliases refer to different image bytes')
    return dict(aliases=sorted({value.name for value in files}),sha256=digests.pop(),
                bytes=files[0].stat().st_size,artifact_name=files[0].name)


def loaded_sdk(modules,identity):
    images=[item for item in modules if looks_like_sdk(item['name'])]
    require(len(images)==1,'Expected exactly one loaded shared SDK image')
    require(images[0]['name'] in identity['aliases'],'Loaded SDK name is not an actual installed alias')
    file=Path(images[0]['path'])
    require(file.is_file() and hashlib.sha256(file.read_bytes()).hexdigest()==identity['sha256'],
            'Loaded SDK bytes differ from installed provider')
    return images[0]


def platform_artifacts(entries,source,run,attempt):
    expected={f'reader-wave3-s19-{key}-{run}-{attempt}' for key in ('linux','windows','macos')}
    require(len(entries)==3 and {item['name'] for item in entries}==expected,
            'Expected exactly the three platform artifacts, not the future evidence artifact')
    for item in entries:
        require(item['workflow_run']['id']==int(run) and item['workflow_run']['head_sha']==source,
                'Artifact belongs to another source or run')
        require(item.get('expired') is False and isinstance(item['size_in_bytes'],int) and item['size_in_bytes']>0,
                'Artifact expired or empty')
        require(re.fullmatch(r'sha256:[0-9a-f]{64}',item.get('digest','')),'Artifact digest missing or malformed')
        require(bool(item.get('expires_at')),'Artifact expiry missing')
    return {item['name']:item for item in entries}
