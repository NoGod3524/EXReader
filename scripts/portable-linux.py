"""Package the Linux executable with notices, using the system WebKit runtime."""
import argparse
import pathlib
import shutil
import tarfile

parser = argparse.ArgumentParser()
parser.add_argument("--binary", default="src-tauri/target/release/exreader")
args = parser.parse_args()
binary = pathlib.Path(args.binary)
if not binary.is_file():
    parser.error(f"Executable not found: {binary}")
folder = pathlib.Path("release/EXReader-Linux-system-webkit")
folder.mkdir(parents=True, exist_ok=True)
shutil.copyfile(binary, folder / "exreader")
(folder / "exreader").chmod(0o755)
for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
    shutil.copyfile(name, folder / name)
shutil.copytree("public/licenses", folder / "licenses", dirs_exist_ok=True)
(folder / "README.txt").write_text(
    "EXReader 0.1.0 — Linux x64\n\n"
    "Extract and run ./exreader. The app itself needs no installation.\n"
    "Requires system WebKitGTK 4.1 and GTK 3, tested on Ubuntu 22.04.\n"
    "Ubuntu runtime dependencies: sudo apt install libwebkit2gtk-4.1-0 libayatana-appindicator3-1\n"
    "Library data uses the current user's system application-data directory.\n"
    "Use Settings > Export library to back up or move your books.\n"
    "Use the larger AppImage package when you need bundled runtime libraries.\n",
    encoding="utf-8",
)
archive = pathlib.Path("release/EXReader-Linux-x64-system-webkit.tar.gz")
with tarfile.open(archive, "w:gz") as tar:
    tar.add(folder, arcname=folder.name, filter=lambda info: info)
print(f"Linux system-WebKit package: {archive.stat().st_size / 1024 ** 2:.1f} MiB")
