#!/usr/bin/env bash
set -euo pipefail
harness="$PWD"; target="$PWD/target"
mkdir -p evidence
for mode in OFF ON; do
 for config in normal scale2 dark large; do
  scale=1; font=11; theme=Adwaita
  case "$config" in scale2) scale=2;; dark) theme=Adwaita-dark; font=16;; large) theme=HighContrast; font=20;; esac
  configdir="$RUNNER_TEMP/d03-$mode-$config"; mkdir -p "$configdir/gtk-3.0"
  printf '[Settings]\ngtk-theme-name=%s\ngtk-font-name=Sans %s\ngtk-xft-dpi=98304\ngtk-application-prefer-dark-theme=%s\n' "$theme" "$font" "$([[ "$config" == dark ]] && echo true || echo false)" > "$configdir/gtk-3.0/settings.ini"
  export XDG_CONFIG_HOME="$configdir" GDK_SCALE="$scale" GDK_DPI_SCALE=1 GTK_THEME="$theme" GTK_A11Y=atspi
  unset NO_AT_BRIDGE || true
  xvfb-run -a -s '-screen 0 2560x1920x24 -dpi 96' dbus-run-session -- bash -euc '
    openbox > "$1/evidence/$2-$3-openbox.log" 2>&1 &
    trap "kill $! || true" EXIT
    gsettings set org.gnome.desktop.interface toolkit-accessibility true
    gsettings set org.gnome.desktop.a11y.applications screen-reader-enabled true
    gdbus call --session --dest org.a11y.Bus --object-path /org/a11y/bus --method org.a11y.Bus.GetAddress
    /usr/bin/python3 "$1/tests/reader_final_d03/audit.py" --payload "$1/target/build/d03-package-$2/EXReader-Linux" --output "$1/evidence/$2-$3" --mode "$2"
  ' bash "$harness" "$mode" "$config" 2>&1 | tee "evidence/$mode-$config.log"
 done
done
python3 - <<'PY'
import hashlib,json,os
from pathlib import Path
files=list(Path('target/build/reading-library/stage').rglob('*.a'))+list(Path('target/build').glob('d03-*/CMakeCache.txt'))
identity=dict(harness_sha=os.environ['GITHUB_SHA'],target_sha='9fc407a5cce5a0bfe644a60bd8dc29f84dea6d0e',sdk_source='edddc463c06ed5731195cdb8f06b2df6dff7699e',run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],files={str(p):dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files})
Path('evidence/identities.json').write_text(json.dumps(identity,indent=2))
print(json.dumps(identity))
PY
