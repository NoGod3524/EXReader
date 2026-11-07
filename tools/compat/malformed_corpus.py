#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Deterministic damaged-EPUB campaign. Book bytes only live in temporary files.

Run: python tools/compat/malformed_corpus.py --engine PATH --font PATH
Replay: same options plus --case CATEGORY-NNN (does not overwrite evidence).
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import warnings
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BASELINE = Path(r"C:\Users\Oscar\Documents\Codex\exr-cjk-corpus\tangshi300-52323.epub")
BASELINE_SHA256 = "a01c08ffa644c02b1e4cfb3bbf70594b765d98f92769ca75da0a4826f5c4c945"
PER_CATEGORY = 128
TIMEOUT = 3
WORKERS = 8
CATEGORIES = {
    "tail": "下载中断：删除文件尾部",
    "middle": "中段字节缺失",
    "directory": "ZIP 中央目录声明与实际不符",
    "container": "缺少 META-INF/container.xml",
    "mimetype": "mimetype 内容不符",
    "case": "内部路径大小写不一致",
    "missing": "OPF 引用了不存在的资源",
    "duplicate": "同一资源出现两次",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Corpus:
    def __init__(self, data):
        self.data = data
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.entries = [(i, archive.read(i)) for i in archive.infolist()]
            self.directory = archive.start_dir
        container = dict((i.filename, b) for i, b in self.entries)["META-INF/container.xml"]
        self.opf = next(e.attrib["full-path"] for e in ET.fromstring(container).iter()
                        if e.tag.endswith("}rootfile"))
        self.opf_data = next(b for i, b in self.entries if i.filename == self.opf)

    def repack(self, entries):
        output = io.BytesIO()
        with warnings.catch_warnings(), zipfile.ZipFile(output, "w") as archive:
            warnings.simplefilter("ignore", UserWarning)  # intentional duplicate names
            for info, body in entries:
                archive.writestr(info, body)
        return output.getvalue()

    def generate(self, category, index):
        """Return bytes and the exact mutation recipe; indices are 1..128."""
        n = index - 1
        data = self.data
        if category == "tail":
            removed = 1 + n * (len(data) - 2) // (PER_CATEGORY - 1)
            return data[:-removed], {"operation": "delete_tail", "bytes": removed}
        if category == "middle":
            start = 32 + (n + 1) * (self.directory - 600) // (PER_CATEGORY + 1)
            length = 1 + n * 2
            return data[:start] + data[start + length:], {
                "operation": "delete_range", "offset": start, "bytes": length}
        if category == "directory":
            # Fixed-width ZIP fields, deliberately retaining all actual file data.
            eocd = data.rfind(b"PK\x05\x06")
            fields = [(self.directory + 42, 4, "local_header_offset"),
                      (self.directory + 20, 4, "compressed_size"),
                      (self.directory + 24, 4, "uncompressed_size"),
                      (self.directory + 28, 2, "filename_length"),
                      (eocd + 16, 4, "central_directory_offset"),
                      (eocd + 12, 4, "central_directory_size"),
                      (eocd + 10, 2, "entry_count")]
            offset, width, name = fields[n % len(fields)]
            original = int.from_bytes(data[offset:offset + width], "little")
            value = original + 1 + n // len(fields)
            mutated = bytearray(data)
            mutated[offset:offset + width] = value.to_bytes(width, "little")
            return bytes(mutated), {"operation": "write_zip_field", "field": name,
                                    "offset": offset, "width": width, "value": value}
        entries = []
        recipe = {"operation": category}
        if category == "case":
            # Toggle a nonempty subset of alphabetic characters of the OPF ZIP name.
            letters = [p for p, c in enumerate(self.opf) if c.isalpha()]
            name = list(self.opf)
            for bit, pos in enumerate(letters):
                if index & (1 << bit):
                    name[pos] = name[pos].swapcase()
            recipe["renamed_opf"] = "".join(name)
        if category in ("missing", "duplicate"):
            root = ET.fromstring(self.opf_data)
            manifest = next(e for e in root if e.tag.endswith("}manifest"))
            items = list(manifest)
            if category == "missing":
                # Alter a resource required by the spine, not an unused manifest item.
                spine = next(e for e in root if e.tag.endswith("}spine"))
                idref = list(spine)[n % len(spine)].attrib["idref"]
                item = next(e for e in items if e.attrib["id"] == idref)
                item.set("href", f"missing-{index:03d}.xhtml")
                recipe.update(idref=idref, href=item.attrib["href"])
            else:
                item = copy.deepcopy(items[n % len(items)])
                item.set("id", f"duplicate-{index:03d}")
                manifest.append(item)
                recipe.update(href=item.attrib["href"], duplicate_id=item.attrib["id"],
                              zip_name=self.entries[n % len(self.entries)][0].filename)
            opf = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        # Missing-container cases also remove subsets of seven other members. This
        # gives 128 different structural losses rather than changing ZIP comments.
        removable = [i.filename for i, _ in self.entries
                     if i.filename not in ("mimetype", "META-INF/container.xml")][:7]
        removed = {"META-INF/container.xml"} | {
            name for bit, name in enumerate(removable) if n & (1 << bit)}
        for info, body in self.entries:
            info = copy.copy(info)
            if category == "container" and info.filename in removed:
                continue
            if category == "case" and info.filename == self.opf:
                info.filename = recipe["renamed_opf"]
            if category == "mimetype" and info.filename == "mimetype":
                body = f"application/damaged-epub-{index:03d}+zip".encode("ascii")
                recipe["replacement_ascii"] = body.decode("ascii")
            if category in ("missing", "duplicate") and info.filename == self.opf:
                body = opf
            entries.append((info, body))
        if category == "container":
            recipe["removed_members"] = sorted(removed)
        if category == "duplicate":
            info, body = self.entries[n % len(self.entries)]
            entries.append((copy.copy(info), body))
        return self.repack(entries), recipe


def classify(code, stderr, timed_out=False):
    if timed_out:
        return "timeout", "timeout"
    if code < 0 or code > 128:
        return "investigate", "abnormal_exit"
    if code == 0:
        return "investigate", "accepted_malformed"
    if not stderr.strip():
        return "investigate", "no_error_text"
    return "passed", "explicit_rejection"


def probe(data, engine, font):
    with tempfile.TemporaryDirectory(prefix="exreader-malformed-") as directory:
        path = Path(directory) / "input.epub"
        path.write_bytes(data)
        started = time.perf_counter()
        timed_out = False
        # check-document is the direct engine process, with no shell or child workers.
        with subprocess.Popen([str(engine), str(path), str(font)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            try:
                stdout, stderr = process.communicate(timeout=TIMEOUT)
            except subprocess.TimeoutExpired:
                timed_out = True
                process.kill()
                stdout, stderr = process.communicate()
            code = process.returncode
        elapsed = time.perf_counter() - started
    stderr = stderr.decode("utf-8", errors="replace")
    bucket, reason = classify(code, stderr, timed_out)
    try:
        report = json.loads(stdout)
    except (ValueError, UnicodeError):
        report = {}
    return {"bucket": bucket, "reason": reason, "exit_code": code,
            "stderr_first_line": stderr.splitlines()[0] if stderr.splitlines() else "",
            "has_error_text": bool(stderr.strip()), "elapsed_seconds": round(elapsed, 6),
            "timed_out": timed_out,
            "engine_status": report.get("status"), "engine_stage": report.get("stage"),
            "engine_version": report.get("engine_version"),
            "complete": report.get("complete")}


def signature(result):
    return tuple(result[k] for k in ("bucket", "reason", "exit_code", "engine_status",
                                     "engine_stage", "stderr_first_line"))


def command(args, case, minimized=False):
    # PowerShell single-quoted arguments preserve Windows paths and apostrophes.
    values = ["python", "tools/compat/malformed_corpus.py", "--baseline", str(args.baseline),
              "--engine", str(args.engine), "--font", str(args.font), "--case", case]
    if minimized:
        values += ["--minimized", str(args.output / "minimized.json")]
    return " ".join("'" + v.replace("'", "''") + "'" if any(c in v for c in " '\\")
                    else v for v in values)


def minimize(data, expected, args):
    """ddmin deletions; record only offsets, never book bytes. Preserve signature.

    Two matching runs are required for every retained reduction. The final sweep
    establishes 1-minimality under byte deletion (not a global size minimum).
    """
    steps, attempts = [], 0
    granularity = 2
    while len(data):
        chunk = max(1, (len(data) + granularity - 1) // granularity)
        reduced = False
        for offset in range(0, len(data), chunk):
            length = min(chunk, len(data) - offset)
            candidate = data[:offset] + data[offset + length:]
            first = probe(candidate, args.engine, args.font)
            attempts += 1
            if signature(first) != expected:
                continue
            second = probe(candidate, args.engine, args.font)
            attempts += 1
            if signature(second) == expected:
                steps.append({"offset": offset, "bytes": length})
                data = candidate
                granularity = max(2, granularity - 1)
                reduced = True
                break
        if not reduced:
            if chunk == 1:
                break
            granularity = min(len(data), granularity * 2)
    return {"delete_steps": steps, "size": len(data), "sha256": sha(data),
            "attempts": attempts, "result": probe(data, args.engine, args.font)}


def write_report(args, metadata, records, minimized):
    counts = Counter(r["bucket"] for r in records)
    pending = [r for r in records if r["bucket"] != "passed"]
    lines = ["# 输入容错错误处理覆盖报告（2026-11-07）", "",
             f"总数 **{len(records)}**；通过 **{counts['passed']}**；待查异常/未明确拒绝 "
             f"**{counts['investigate']}**；待查超时 **{counts['timeout']}**。",
             f"通过率 **{counts['passed'] / len(records):.2%}**；待查合计 **{len(pending)}**。",
             "三类互斥，计数相加等于总数。返回 0 的损坏文件也登记为待查。", "",
             "## 执行条件与判定", "",
             f"- 引擎源码：`{metadata['source_commit']}`；版本：`{metadata['engine_version']}`。",
             f"- 基线：`{args.baseline}`；SHA-256：`{metadata['baseline_sha256']}`。",
             f"- CLI：`{args.engine}`；SHA-256：`{metadata['engine_sha256']}`。",
             f"- 字体：`{args.font}`；SHA-256：`{metadata['font_sha256']}`。",
             f"- {metadata['platform']}；Python {platform.python_version()}；8 路线程调度，"
             "每个文件单独启动原生 CLI 子进程，communicate 超时 3 秒后 kill 并回收。",
             "- CLI 参数为 `exreader-check-document input.epub font.ttf`，不设页数上限，"
             "遍历全部章节和页面；有效基线须在相同超时内返回 0。",
             "- 通过：非 0 且不属于异常退出，stderr 有非空错误说明。待查：返回 0、"
             "非 0 无错误文本、负退出码或退出码 >128；超时单列。",
             "- 数值错误码取 stdout JSON 的 status（engine_status），同时记录退出码、"
             "stage、stderr 首行和从启动到回收的耗时。stderr 为空不会因 JSON 有 status 而通过。",
             "- 每类 128 个，共 1024 个内容 SHA-256 唯一的变体；无 ZIP 注释填充。",
             "- `results.jsonl` 保存全部原始测量和结构生成步骤；`replays.jsonl` 保存每条待查的"
             "两次独立复跑结果。文件字节只在系统临时目录生成，进程回收后删除。", "",
             "## 按类别分布", "",
             "| 类别 | 总数 | 通过 | 待查异常/未明确拒绝 | 超时 | 无错误文本且非0 | 返回0 | >128/信号 |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    no_text = []
    for category, label in CATEGORIES.items():
        subset = [r for r in records if r["category"] == category]
        c = Counter(r["bucket"] for r in subset)
        reasons = Counter(r["reason"] for r in subset)
        no_text_count = sum(not r['has_error_text'] for r in subset)
        if no_text_count:
            no_text.append(f"{label}：{no_text_count}/128 无明确错误文本")
        lines.append(f"| {category}：{label} | {len(subset)} | {c['passed']} | "
                     f"{c['investigate']} | {c['timeout']} | {reasons['no_error_text']} | "
                     f"{reasons['accepted_malformed']} | {reasons['abnormal_exit']} |")
    lines += ["", "## 目前缺少明确错误文本的类别", ""]
    lines += [f"- {item}。" for item in no_text] or ["所有类别的样本都有明确错误文本。"]
    if no_text:
        lines += ["", "上表将返回 0 的静默接受与非 0 无错误文本分开统计。"
                  "待查表示未满足本任务的明确拒绝标准，不等同于已确认的进程崩溃。"]
    directory_pending = [r for r in pending if r["category"] == "directory"]
    if directory_pending:
        fields = Counter(r["recipe"]["field"] for r in directory_pending)
        lines += ["", "目录待查按字段分布（首个中央目录条目为 mimetype）：" +
                  "、".join(f"`{field}` {count} 个" for field, count in fields.items()) + "。"]
    lines += ["", f"待查项复跑：{metadata['replay_count']} 条各复跑两次；"
              f"不一致 {len(metadata['unstable_replays'])} 条。",
              f"主测试耗时 {metadata['campaign_seconds']:.3f} 秒；"
              f"单例最大耗时 {max(r['elapsed_seconds'] for r in records):.6f} 秒。"]
    lines += ["", "## 确定性生成规则", "",
              "编号为 001..128；精确偏移、字段值和移除成员名见 results.jsonl 的 recipe。", "",
              "- tail：删除尾部 1..基线长度−1 字节的 128 个等距截断点。",
              "- middle：在首个本地头之后、中央目录之前的 128 个位置删除 1..255 个字节。",
              "- directory：轮换修改首个中央目录条目的本地头偏移、压缩/原始长度、文件名长度，"
              "或 EOCD 的目录偏移/长度/条目数；其余字节不动。",
              "- container：移除 container.xml，并组合移除七个其他成员的子集；编号 001 仅删除 container.xml。",
              "- mimetype：替换为不同的无效 ASCII 媒体类型。",
              "- case：只切换 ZIP 中 OPF 路径的字母大小写，保留 container.xml 中的原路径。",
              "- missing：轮换把 spine 必需资源的 manifest href 改为不存在的 missing-NNN.xhtml。",
              "- duplicate：OPF 增加相同 href、不同 id 的条目，同时轮换重复一个 ZIP 成员。",
              "", "## 异常退出/卡住的最小化", ""]
    if minimized:
        lines += ["按相同退出码、状态、阶段和 stderr 首行分组，每组一个代表做字节删除 ddmin；"
                  "每次缩减须连续两次保留签名，最终逐字节删除扫描。",
                  "`minimized.json` 仅含基线哈希、代表编号、顺序删除步骤和结果，不含任何正文。"]
        for item in minimized:
            lines += ["", f"- {item['case']}：{item['original_size']} → {item['size']} 字节；"
                      f"{item['attempts']} 次探测；复跑：`{command(args, item['case'], True)}`。"]
    else:
        lines += ["本次未发现异常退出、非 0 无错误文本或超时，无需生成最小化配方。"]
    lines += ["", "## 待查清单", "",
              "每行命令在仓库根目录 PowerShell 执行，重新从 SHA-256 校验后的基线生成样本并启动独立 CLI；"
              "无需保存或下载变体。exit_code 为超时强制终止时的 OS 返回值时，以 timed_out 字段为准。", "",
              "| 编号 | 类别 | 退出码 | 原因 | status/stage | 一条复跑命令 |",
              "|---|---|---:|---|---|---|"]
    for r in pending:
        lines.append(f"| {r['case']} | {r['category']} | {r['exit_code']} | {r['reason']} | "
                     f"{r['engine_status']}/{r['engine_stage']} | `{command(args, r['case'])}` |")
    lines += ["", "## 完整复跑", "", "```powershell",
              command(args, "tail-001").rsplit(" --case", 1)[0] +
              " --output evidence/malformed-input-20261107", "```", "",
              "本次只登记错误处理覆盖问题，不修改引擎；本地构建参数及哈希记录在 metadata.json。", "",
              "如需重建 CLI，在本报告记录的源码提交上运行（构建目录位于仓库外）：", "",
              "```powershell",
              'cmake -S . -B "$env:TEMP/exreader-malformed-build" -G Ninja -DCMAKE_BUILD_TYPE=Release '
              '-DEXR_BUILD_TESTS=OFF -DEXR_BUILD_TOOLS=ON -DEXR_ENABLE_IMAGE_AVIF=OFF '
              '-DEXR_ENABLE_IMAGE_TIFF=OFF -DEXR_ENABLE_IMAGE_WEBP=OFF -DEXR_ENABLE_ICC=OFF '
              '-DEXR_ENABLE_MP3=OFF -DEXR_ENABLE_PDF_CRYPTO=OFF -DEXR_ENABLE_PDF_JPX=OFF',
              'cmake --build "$env:TEMP/exreader-malformed-build" --target exreader-check-document --parallel 8',
              "```", "",
              "随后将复跑命令中的 --engine 改为该目录下的 exreader-check-document.exe。", ""]
    (args.output / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--font", type=Path, default=ROOT / "tests/fixtures/fonts/primary.ttf")
    parser.add_argument("--output", type=Path, default=ROOT / "evidence/malformed-input-20261107")
    parser.add_argument("--case", help="Replay one case, e.g. tail-001")
    parser.add_argument("--minimized", type=Path, help="Replay deletion recipe for --case")
    args = parser.parse_args()
    args.baseline, args.engine, args.font = (p.resolve(strict=True) for p in
                                          (args.baseline, args.engine, args.font))
    data = args.baseline.read_bytes()
    if sha(data) != BASELINE_SHA256:
        parser.error(f"baseline SHA-256 mismatch: expected {BASELINE_SHA256}, got {sha(data)}")
    corpus = Corpus(data)
    if args.case:
        try:
            category, number = args.case.rsplit("-", 1)
            index = int(number)
            assert category in CATEGORIES and 1 <= index <= PER_CATEGORY
        except (ValueError, AssertionError):
            parser.error("--case must be CATEGORY-001..128")
        mutated, recipe = corpus.generate(category, index)
        if args.minimized:
            manifest = json.loads(args.minimized.read_text(encoding="utf-8"))
            assert manifest["baseline_sha256"] == sha(data)
            item = next(r for r in manifest["groups"] if r["case"] == args.case)
            for step in item["delete_steps"]:
                start, length = step["offset"], step["bytes"]
                mutated = mutated[:start] + mutated[start + length:]
            assert sha(mutated) == item["sha256"]
        print(json.dumps({"case": args.case, "sha256": sha(mutated), "recipe": recipe,
                          **probe(mutated, args.engine, args.font)}, ensure_ascii=False))
        return
    if args.minimized:
        parser.error("--minimized requires --case")
    baseline_result = probe(data, args.engine, args.font)
    if baseline_result["exit_code"] != 0 or baseline_result["timed_out"] or not baseline_result["complete"]:
        raise RuntimeError(f"baseline must complete within 3 seconds: {baseline_result}")
    normalized = corpus.repack(corpus.entries)
    control_result = probe(normalized, args.engine, args.font)
    if control_result["exit_code"] != 0 or not control_result["complete"]:
        raise RuntimeError(f"unchanged repack control failed: {control_result}")
    baseline_result.update(bucket="control", reason="valid_baseline")
    control_result.update(bucket="control", reason="unchanged_repack")
    jobs = [(category, index) for category in CATEGORIES for index in range(1, PER_CATEGORY + 1)]
    records, hashes = [], set()
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()

    def run(job):
        category, index = job
        mutated, recipe = corpus.generate(category, index)
        return {"case": f"{category}-{index:03d}", "category": category,
                "sha256": sha(mutated), "size": len(mutated), "recipe": recipe,
                **probe(mutated, args.engine, args.font)}

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for future in as_completed([pool.submit(run, job) for job in jobs]):
            result = future.result()
            assert result["sha256"] not in hashes, "duplicate corpus bytes"
            hashes.add(result["sha256"])
            records.append(result)
            if len(records) % 128 == 0:
                print(f"{len(records)}/1024 {dict(Counter(r['bucket'] for r in records))}", flush=True)
    campaign_seconds = time.perf_counter() - started
    records.sort(key=lambda r: r["case"])
    (args.output / "results.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    pending = [r for r in records if r["bucket"] != "passed"]
    replays = []

    def replay(record):
        category, number = record["case"].rsplit("-", 1)
        mutated, _ = corpus.generate(category, int(number))
        attempts = [probe(mutated, args.engine, args.font) for _ in range(2)]
        return {"case": record["case"], "stable": all(signature(a) == signature(record) for a in attempts),
                "attempts": attempts}

    print(f"Replaying {len(pending)} pending cases twice", flush=True)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        replays = list(pool.map(replay, pending))
    (args.output / "replays.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in replays), encoding="utf-8")
    # Reduce one representative per identical failure signature; all original
    # pending cases retain their own independently verified replay commands.
    groups = {}
    for r in pending:
        if r["reason"] in ("abnormal_exit", "no_error_text", "timeout"):
            groups.setdefault(signature(r), []).append(r)
    minimized = []
    for expected, members in groups.items():
        record = members[0]
        category, number = record["case"].rsplit("-", 1)
        mutated, _ = corpus.generate(category, int(number))
        print(f"Minimizing {record['case']} ({len(members)} matching cases)", flush=True)
        minimized.append({"case": record["case"], "members": [r["case"] for r in members],
                          "original_size": len(mutated), **minimize(mutated, expected, args)})
    (args.output / "minimized.json").write_text(json.dumps(
        {"baseline_sha256": sha(data), "groups": minimized}, indent=2), encoding="utf-8")
    metadata = {"schema": 1, "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                                         text=True).strip(),
                "platform": platform.platform(), "python": sys.version,
                "baseline_sha256": sha(data), "engine_sha256": sha(args.engine.read_bytes()),
                "font_sha256": sha(args.font.read_bytes()), "engine_version": baseline_result['engine_version'],
                "harness_sha256": sha(Path(__file__).read_bytes()),
                "engine": str(args.engine), "font": str(args.font), "baseline": str(args.baseline),
                "baseline_result": baseline_result, "repack_control_result": control_result,
                "workers": WORKERS, "timeout_seconds": TIMEOUT, "per_category": PER_CATEGORY,
                "total": len(records), "unique_sha256": len(hashes),
                "counts": {key: sum(r["bucket"] == key for r in records)
                           for key in ("passed", "investigate", "timeout")},
                "replay_count": len(replays), "unstable_replays": [r["case"] for r in replays if not r["stable"]],
                "campaign_seconds": round(campaign_seconds, 3)}
    cache = args.engine.parent / "CMakeCache.txt"
    if cache.exists():
        metadata["cmake_configuration"] = [line for line in cache.read_text().splitlines()
                                           if line.startswith(("EXR_", "CMAKE_BUILD_TYPE:", "CMAKE_C_COMPILER:"))]
    metadata["runtime_libraries"] = {p.name: sha(p.read_bytes()) for p in
                                     args.engine.parent.glob("*exreader*.dll")}
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    write_report(args, metadata, records, minimized)
    print(json.dumps({"total": len(records), "counts": metadata["counts"],
                      "unstable_replays": metadata["unstable_replays"]}), flush=True)


if __name__ == "__main__":
    main()
