"""Additive scope admission; unchanged accepted SDK identity/semantic audit."""
import argparse, hashlib, importlib.util, json, os, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BASE='0f6780328fc70ff187be3fa59aa6875bfbf80296'
OWN=('tests/gtk_native_conflict_resolution_sdk342/',)
FILES={'.github/workflows/gtk-native-conflict-resolution-sdk342.yml','docs/gtk-native-conflict-resolution-sdk342/STATUS.md'}
sys.path.insert(0,str(ROOT/'tests/windows_gtk_conflict_recovery'))
import sdk342_identity as retained

def guard():
    retained.actions_only()
    subprocess.run(['git','merge-base','--is-ancestor',BASE,'HEAD'],cwd=ROOT,check=True)
    changed=retained.git('diff','--name-only',BASE,'HEAD').splitlines()
    assert changed and all(p in FILES or p.startswith(OWN) for p in changed),changed
    assert not retained.git('diff','--name-only','HEAD','--')
    # Pin every byte of the original native scenario except the validated
    # activation sequence. This does not exempt any assertion or timeout.
    probe_blob='220550d847fbf17a812fb56a7cb391cc9b85c403'
    old_probe=subprocess.check_output(['git','show',probe_blob],cwd=ROOT)
    old_action=b"        click('Resolve versions');click('Yes');wait(lambda:enabled('Save'))\n"
    new_action=(b"        # Native mnemonic avoids entering GTK's nested confirmation loop from\n"
                b"        # an AT-SPI action callback; the real Yes confirmation remains required.\n"
                b"        target=window('Book details');assert command('xdotool','getactivewindow')==target\n"
                b"        host.key('alt+r');click('Yes');wait(lambda:enabled('Save'))\n")
    probe=(ROOT/'tests/gtk_native_conflict_resolution_sdk342/gtk.py').read_bytes()
    assert old_probe.count(old_action)==1 and probe==old_probe.replace(old_action,new_action,1)
    print('GTK_NATIVE_ACTIVATION_EQUIVALENCE '+json.dumps({'baseline_blob':probe_blob,'current_sha256':hashlib.sha256(probe).hexdigest(),'only_delta':'PID-scoped active Book details native Alt+R activation; exact Yes confirmation, all assertions and budgets retained'}),flush=True)
    # Extend only the allowed additive-path set. Every imported product blob,
    # old semantic assertion, SDK tree, identity measurement and budget remains.
    retained.NEW_PATHS.update(changed)
    return retained.guard()

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('guard','collect','audit'));p.add_argument('--platform',choices=('gtk','windows'));a=p.parse_args()
    guard()
    if a.mode=='collect':retained.collect(a.platform)
    elif a.mode=='audit':retained.audit()
if __name__=='__main__':main()
