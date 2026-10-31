#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""J02: write platform-specific Chinese backup/upgrade/recovery instructions into
the six retained delivery packages (Android consumes the J01 candidate) and
verify the result. Execute ONLY in GitHub Actions."""
import hashlib, importlib.util, io, json, os, sys, zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[3]
F12 = Path(os.environ["F12_CHECKOUT"]).resolve()
SRC = Path(os.environ["SOURCE_CHECKOUT"]).resolve()
OUT = ROOT / "j02-evidence"
CAND = ROOT / "j02-candidates"

spec = importlib.util.spec_from_file_location("f12", F12 / "scripts/audit/dot_f12_package_material_audit_20261030.py")
f12 = importlib.util.module_from_spec(spec); spec.loader.exec_module(f12)
sha, need, js, dump = f12.sha, f12.need, f12.js, f12.dump
MIB = f12.MIB
J01_ART = (13023043154, 19726819, "372ee0aee5222afe077e1dbb10f2547a47919c22c717ed7f4797f895c033e6e1")
J01_OUTER_SHA = "944ead0934115f7a92a03e500417b1a0398cf05f29675a7096970f1a0a267f55"
J01_NAME = "exreader-android-j01-candidate.zip"
UPGRADE_DOC = "docs/READER-UPGRADE-DELIVERY.md"
EXTRA_DOC = "升级与交付状态-项目原文.md"

REQUIRED = ["## 备份", "## 升级", "## 升级失败", "## 校验", "## 范围与限制", "## 尚未验证"]

COMMON_BACKUP = """\
- 先完全退出应用。**不要在应用运行时复制 SQLite 数据库文件**（含 -wal / -shm 旁文件）。
- 需要保留的数据分三类：SDK 书库、产品目录（两者是各自独立的存储）、已导入的原始书籍文件，以及偏好设置；只备份其中一类不足以恢复。
- 本包只含应用程序与说明，**没有随包提供备份/恢复工具**；应用内是否提供备份入口，当前证据中未确认。
- 备份后用文件大小与 SHA-256 记录每个备份文件，并保留到新版本验证完毕。"""

COMMON_FAIL = """\
遇到以下任一情况请**立即停止继续使用新版本，并停止同步**：
- 新版本无法启动、提示书库/目录错误，或书籍、阅读位置、标注数量与升级前不一致；
- SHA256SUMS 校验失败（见“校验”）。

恢复步骤：
1. 退出新版本，不要删除新版本产生的数据，先整体改名保留以便排查。
2. 恢复升级前的备份（书库、产品目录、原始文件、偏好设置须同一时间点成套恢复）。
3. 重新启用升级前保留的旧版本，打开后逐本核对书籍与阅读记录。
4. 记录新旧包的 SHA-256 和现象，再决定是否重试。

数据风险：同步（WebDAV）不是备份，且同步不同步实时 SQLite 数据库；已同步到其他设备的记录不会因本机恢复而回滚。旧版 IndexedDB 迁移工具不得对可能被其他进程打开的书库运行，详见随附的《升级与交付状态》原文。"""

PLATFORM = {
 "windows": dict(
  upgrade="""\
1. 退出 EXReader，完成上节备份。
2. 将新 ZIP 解压到一个**全新空目录**，不要覆盖旧目录；旧目录原样保留。
3. 只运行其中一个版本，运行 `EXReader\\EXReader.exe`；不要让新旧版本同时打开同一书库。
4. 成功判断：能打开原有书籍，阅读位置与标注数量与升级前一致。
注：本包无安装器，不写注册表。已读取到的宿主源码显示 Windows 宿主把偏好等文件放在其 data_dir 下（如 preferences.json、fonts），但默认 data_dir 的具体位置未在随包证据中确认；请以应用设置中显示的书库位置为准。""",
  extra=["未做 Authenticode 签名，SmartScreen 可能拦截。"]),
 "linux": dict(
  upgrade="""\
1. 退出 EXReader，完成上节备份。
2. 解压到全新目录，旧目录保留；运行新目录中的 `EXReader-Linux/Start-EXReader.sh`（需要 GTK3）。
3. 书库和状态保存在当前用户数据目录（具体子目录未在随包证据中确认），不在程序目录内——因此换目录不会自动带走数据，也不会自动隔离新旧版本；请只开一个版本。
4. 成功判断：能打开原有书籍，阅读位置与标注数量与升级前一致。""",
  extra=["仅在 Ubuntu 22.04 上验证。"]),
 "macos": dict(
  upgrade="""\
1. 退出 EXReader，完成上节备份。
2. 把旧的 EXReader.app 改名保留（例如 EXReader-旧.app），再放入新的 EXReader.app，不要直接覆盖。
3. 首次打开如被 Gatekeeper 拦截，需要手动放行（仅 ad-hoc 签名，无公证）。
4. 成功判断：能打开原有书籍，阅读位置与标注数量与升级前一致。
书库默认位置未在随包证据中确认。""",
  extra=["仅在 macOS 15 构建机上验证。"]),
 "android": dict(
  upgrade="""\
1. 先完成上节备份，再升级。**卸载应用会删除应用私有数据**，请不要把“先卸载再安装”当成升级方式。
2. 使用 `adb install -r artifacts/app-debug.apk` 覆盖安装。Android 要求新旧 APK 包名一致且签名一致才能保留数据；本包是 debug 签名，若与旧版本签名不同，会出现 INSTALL_FAILED_UPDATE_INCOMPATIBLE，此时请停止，不要卸载旧版本。
3. 成功判断：启动 org.exreader.host，原有书籍与阅读记录仍在。
注：Android 书库位于应用私有目录；测试驱动使用 getFilesDir() 下的书库，生产路径以应用为准，随包证据未完整确认。""",
  extra=["本包基于 J01 许可材料候选：licenses/ 目录含补入的许可文本，APK 字节未变。",
         "只验证 x86_64 API 34 模拟器。"]),
 "iphone": dict(
  upgrade="""\
1. 先完成备份。对模拟器：`xcrun simctl uninstall` 会删除应用容器内的数据，请不要用卸载代替升级。
2. 使用 `xcrun simctl install <udid> EXReader.app` 安装新包，再 `xcrun simctl launch <udid> org.exreader.host`。同一 bundle id 的覆盖安装是否保留书库，本包未验证。
3. 成功判断：原有书籍与阅读记录仍在；否则按“升级失败”处理。""",
  extra=["未签名，不能安装到真机；不是 App Store 包。"]),
 "ipad": dict(
  upgrade="""\
1. 先完成备份。对模拟器：`xcrun simctl uninstall` 会删除应用容器内的数据，请不要用卸载代替升级。
2. 使用 `xcrun simctl install <udid> EXReader.app` 安装新包，再 `xcrun simctl launch <udid> org.exreader.host`。同一 bundle id 的覆盖安装是否保留书库，本包未验证。
3. 成功判断：原有书籍与阅读记录仍在；否则按“升级失败”处理。""",
  extra=["未签名，不能安装到真机；不是 App Store 包。"]),
}
UNVERIFIED = """\
- 从旧版下载包升级到本包的完整过程、降级、真机安装、商店发布、签名升级均**未验证**。
- 上述备份对象的具体磁盘位置，除已标注的以外，未在随包证据中确认。
- 本说明是文字说明，没有对应的自动化功能验证。
- 项目原文《升级与交付状态》随包提供（""" + EXTRA_DOC + """），其中“尚无已验证的六端可安装最终产品”等结论仍然有效。"""


def render(target, original_text, source_sha):
    p = PLATFORM[target]
    s = original_text.rstrip("\n") + "\n\n"
    s += "## 备份\n\n" + COMMON_BACKUP + "\n\n"
    s += "## 升级\n\n" + p["upgrade"] + "\n\n"
    s += "## 升级失败的停止条件与恢复\n\n" + COMMON_FAIL.replace("见“校验”", "见上文“校验”") + "\n\n"
    s += "## 本平台补充限制\n\n" + "\n".join("- " + x for x in p["extra"]) + "\n\n"
    s += "## 尚未验证\n\n" + UNVERIFIED + "\n"
    # headings required by the coverage check
    s = s.replace("## 升级失败的停止条件与恢复", "## 升级失败的停止条件与恢复")
    return s


def fetch_artifact(aid, size, digest):
    raw = f12.get(f"https://api.github.com/repos/{f12.REPO}/actions/artifacts/{aid}/zip", size)
    need(len(raw) == size and sha(raw) == digest, "download.identity")
    return raw


def dumps_like(obj, original_text):
    indent = 2 if original_text.startswith("{\n") else None
    return (json.dumps(obj, ensure_ascii=False, indent=indent) + ("\n" if original_text.endswith("\n") else "")).encode()


def load(raw, expect_inner=None):
    z = zipfile.ZipFile(io.BytesIO(raw))
    outer = f12.scan_zip(raw, [0], "outer")
    mname = [n for n in outer if PurePosixPath(n).name == "manifest.json"]
    need(len(mname) == 1, "outer.manifest_count")
    om = js(outer[mname[0]])
    arch = [n for n in outer if n == om["archive"]["name"] or n.endswith("/" + om["archive"]["name"])]
    need(len(arch) == 1, "outer.archive_count")
    pkg = outer[arch[0]]
    need(sha(pkg) == om["archive"]["sha256"] and len(pkg) == om["archive"]["bytes"], "outer.inner_hash")
    if expect_inner: need(sha(pkg) == expect_inner, "manifest.inner_hash")
    return dict(z=z, outer=outer, mname=mname[0], om=om, arch=arch[0], pkg=pkg)


def rebuild(a, target, source_doc):
    files = f12.scan_zip(a["pkg"], [0], "package")
    im = f12.manifest_check(files, target)
    iname = im["instructions"]
    orig = files[iname].decode("utf-8")
    need(f12.SOURCE in orig, "instructions.source")
    new_text = render(target, orig, f12.SOURCE).encode("utf-8")
    adds = {iname: new_text, EXTRA_DOC: source_doc}
    mtext = files["manifest.json"].decode()
    man = js(files["manifest.json"])
    sample = next(iter(man["files"].values()))
    for name, data in adds.items():
        row = dict(sample); row["bytes"], row["sha256"] = len(data), sha(data)
        if "mode" in row: row["mode"] = 0o644
        man["files"][name] = row
    man["j02_candidate"] = {"task": "J02", "instructions_file": iname,
        "original_instructions_sha256": sha(files[iname]), "new_instructions_sha256": sha(new_text),
        "added_files": [EXTRA_DOC], "original_inner_sha256": sha(a["pkg"]),
        "note": "documentation only; payload bytes unchanged; not a release"}
    new_manifest = dumps_like(man, mtext)
    sums = "".join(man["files"][n]["sha256"] + "  " + n + "\n" for n in sorted(man["files"])).encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(a["pkg"])) as zin, zipfile.ZipFile(buf, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info)
            if info.filename == "manifest.json": data = new_manifest
            elif info.filename == "SHA256SUMS": data = sums
            elif info.filename == iname: data = new_text
            zout.writestr(info, data, compress_type=info.compress_type)
        zi = zipfile.ZipInfo(EXTRA_DOC, date_time=(2026, 10, 31, 0, 0, 0)); zi.external_attr = 0o100644 << 16
        zout.writestr(zi, source_doc, compress_type=zipfile.ZIP_DEFLATED)
    inner = buf.getvalue()
    om = json.loads(json.dumps(a["om"]))
    om["archive"]["sha256"], om["archive"]["bytes"] = sha(inner), len(inner)
    om["files"] = js(new_manifest)["files"]
    om["j02_candidate"] = man["j02_candidate"]
    otext = a["outer"][a["mname"]].decode()
    new_outer_manifest = dumps_like(om, otext)
    ob = io.BytesIO()
    with zipfile.ZipFile(ob, "w") as zout:
        for info in a["z"].infolist():
            data = a["z"].read(info)
            if info.filename == a["mname"]: data = new_outer_manifest
            elif info.filename == a["arch"]: data = inner
            zout.writestr(info, data, compress_type=info.compress_type)
    return ob.getvalue(), inner, files, iname


def verify(target, outer_bytes, before_files, iname, android_j01_files=None):
    b = load(outer_bytes)
    names = [i.filename for i in b["z"].infolist()]
    need(len(names) == len(set(names)), "cand.duplicate_outer")
    inner_names = [i.filename for i in zipfile.ZipFile(io.BytesIO(b["pkg"])).infolist()]
    need(len(inner_names) == len(set(inner_names)), "cand.duplicate_inner")
    files = f12.scan_zip(b["pkg"], [0], "cand.pkg")
    im = f12.manifest_check(files, target)
    need(b["om"]["files"] == im["files"], "cand.outer_inner_identity")
    skip = {"manifest.json", "SHA256SUMS", iname, EXTRA_DOC}
    need(all(files.get(n) == v for n, v in before_files.items() if n not in skip), "cand.payload_changed")
    need(set(files) == set(before_files) | {EXTRA_DOC}, "cand.inventory")
    text = files[iname].decode("utf-8")
    need(f12.SOURCE in text, "cand.source_line")
    topics = {h: (h in text) for h in REQUIRED[:1] + ["## 升级", "## 升级失败的停止条件与恢复", "## 校验", "## 范围与限制", "## 尚未验证"]}
    need(all(topics.values()), "cand.topics:" + ",".join(k for k, v in topics.items() if not v))
    need(files[EXTRA_DOC] == (SRC / UPGRADE_DOC).read_bytes(), "cand.extra_doc")
    if target == "android":
        need(sha(files[im["entry"]]) == "b6adf2d4208be647573090d77490b63fea9e37e2c89c760b2871fc4aec5f9519", "cand.apk_changed")
        need(all(files.get(n) == v for n, v in android_j01_files.items() if n.startswith("licenses/")), "cand.j01_materials_lost")
        need(any(n.startswith("licenses/") for n in files), "cand.j01_materials_missing")
    return dict(topics=topics, instruction_bytes=len(files[iname]), instruction_sha256=sha(files[iname]),
                inner_sha256=sha(b["pkg"]), members=len(files))


def main():
    need(os.environ.get("GITHUB_ACTIONS") == "true", "actions_only")
    OUT.mkdir(exist_ok=True); CAND.mkdir(exist_ok=True)
    source_doc = (SRC / UPGRADE_DOC).read_bytes()
    manifest, results = {}, {}
    j01_files = None
    for target, (aid, size, digest, inner_digest) in f12.PINS.items():
        meta = js(f12.get(f"https://api.github.com/repos/{f12.REPO}/actions/artifacts/{aid}", MIB))
        f12.meta_check(meta, target)
        if target == "android":
            j = J01_ART
            jm = js(f12.get(f"https://api.github.com/repos/{f12.REPO}/actions/artifacts/{j[0]}", MIB))
            need(jm["digest"] == "sha256:" + j[2] and jm["size_in_bytes"] == j[1] and jm["expired"] is False, "j01.identity")
            jraw = fetch_artifact(*j)
            jzip = f12.scan_zip(jraw, [0], "j01")
            need(set(jzip) == {J01_NAME} and sha(jzip[J01_NAME]) == J01_OUTER_SHA, "j01.outer_identity")
            raw = jzip[J01_NAME]
            a = load(raw)
            j01_files = f12.scan_zip(a["pkg"], [0], "j01.pkg")
            input_id = {"source": "J01 candidate artifact %d" % j[0], "outer_sha256": J01_OUTER_SHA}
        else:
            raw = fetch_artifact(aid, size, digest)
            a = load(raw, inner_digest)
            input_id = {"source": "original F06 artifact %d" % aid, "outer_sha256": digest}
        try:
            outer_bytes, inner_bytes, before, iname = rebuild(a, target, source_doc)
            v = verify(target, outer_bytes, before, iname, j01_files)
            name = f"exreader-{target}-sdk342-j02-candidate.zip"
            (CAND / name).write_bytes(outer_bytes)
            results[target] = dict(status="passed", input=input_id, **v)
            manifest[target] = dict(file=name, bytes=len(outer_bytes), sha256=sha(outer_bytes), **input_id,
                                    original_f06_inner_sha256=inner_digest)
        except Exception as e:
            results[target] = dict(status="failed", input=input_id, error=str(e), type=type(e).__name__)
    ext = {"task": "J02", "sdk_version": "3.42.0", "source": f12.SOURCE, "producer_run": f12.RUN, "producer_attempt": f12.ATTEMPT,
           "packages": manifest, "note": "outer hashes live only here, never inside the ZIPs (no circular hash)"}
    dump(CAND / "six-package-final-manifest.json", ext)
    sums = "".join(m["sha256"] + "  " + m["file"] + "\n" for m in manifest.values())
    (CAND / "SHA256SUMS").write_text(sums)
    summary = dict(results=results, passed=[t for t, r in results.items() if r["status"] == "passed"],
                   failed=[t for t, r in results.items() if r["status"] != "passed"],
                   no_real_device_install=True, release_claimed=False, formal_acceptance="95/108 unchanged")
    dump(OUT / "j02-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if len(summary["passed"]) == 6 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        OUT.mkdir(exist_ok=True)
        dump(OUT / "fatal.json", {"error": str(e), "type": type(e).__name__})
        raise
