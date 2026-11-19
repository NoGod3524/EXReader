# SPDX-License-Identifier: MIT
"""Build the four #267 source arms on current main.

A = pre-#267 sources, B = mask-row reuse only, C = this branch (RGB group
commit only), D = main as merged (#267 both hunks). Only the two #267 files
vary; every arm is built in the same Release tree.
"""
import argparse
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MAIN = "5580d505b"
CHANGE = "d704cdacc"
MASK = "src/pdf_softmask.c"
RGB = "src/blend.c"
# (pdf_softmask.c revision, blend.c revision)
ARMS = {"A": (f"{CHANGE}^", f"{CHANGE}^"), "B": (CHANGE, f"{CHANGE}^"),
        "C": (f"{CHANGE}^", CHANGE), "D": (CHANGE, CHANGE)}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def replace(path, old, new, required=True):
    target = ROOT / path
    source = target.read_bytes().replace(b"\r\n", b"\n")
    assert source.count(old) == 1 or (not required and not source.count(old)), (path, old)
    target.write_bytes(source.replace(old, new))


def instrument():
    """Count mask rows/samples and time the RGBA-to-mask loop; D also counts row reuse."""
    replace(MASK, b"#include <stdio.h>\n", b"#include <stdio.h>\n#include <time.h>\n")
    replace(MASK, b"  pixels = bitmap.pixels;\n",
            b"  size_t reused_rows=0,inrow=0,samples=0;struct timespec t0,t1;"
            b"timespec_get(&t0,TIME_UTC);\n  pixels = bitmap.pixels;\n")
    replace(MASK, b"      memcpy(result+y*width,result+(y-1)*width,width);",
            b"      reused_rows++;\n      memcpy(result+y*width,result+(y-1)*width,width);", required=False)
    replace(MASK, b"{ result[i]=result[i-1];continue; }", b"{ inrow++;result[i]=result[i-1];continue; }")
    replace(MASK, b"      a=pixels[i*4+3]/255.;", b"      samples++;\n      a=pixels[i*4+3]/255.;")
    replace(MASK, b"  status=EXR_OK;\ndone:\n",
            b"  status=EXR_OK;\n  timespec_get(&t1,TIME_UTC);\n"
            b'  fprintf(stderr,"MASK id=%u width=%u rows=%u reused=%zu inrow=%zu samples=%zu ns=%lld\\n",'
            b"mask,width,height,reused_rows,inrow,samples,"
            b"(long long)(t1.tv_sec-t0.tv_sec)*1000000000LL+(t1.tv_nsec-t0.tv_nsec));\ndone:\n")


def build(directory, log, full=False):
    command = ["cmake", "--build", str(directory), "--parallel", "6"]
    if not full:
        command += ["--target", "exreader"]
    with log.open("wb") as stream:
        subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    parser.add_argument("--probe", action="store_true", help="build instrumented C and D DLLs")
    parser.add_argument("--ctest", action="store_true", help="full build and ctest of the working tree")
    args = parser.parse_args()
    directory = args.build.resolve()
    # Main's renderer sources equal the #267 commit; the branch differs only in the mask file.
    assert not git("diff", "--name-only", CHANGE, MAIN, "--", "src", "include", "cmake", "CMakeLists.txt")
    assert git("diff", "--name-only", MAIN, "--", "src", "include", "cmake",
               "CMakeLists.txt").decode().split() == [MASK]
    assert git("show", f"{CHANGE}^:{MASK}") == (ROOT / MASK).read_bytes().replace(b"\r\n", b"\n")
    if args.ctest:
        build(directory, directory / "build-test.log", full=True)
        result = subprocess.run(["ctest", "--test-dir", str(directory), "--parallel", "6",
                                 "--output-on-failure"], cwd=ROOT, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output = result.stdout.replace(str(ROOT), ".").replace(ROOT.as_posix(), ".")
        (HERE / "raw" / "ctest.txt").write_text(output, encoding="utf-8")
        print("\n".join(output.splitlines()[-8:]), flush=True)
        result.check_returncode()
        return
    bins = directory / "arms"
    bins.mkdir(exist_ok=True)
    original = {path: (ROOT / path).read_bytes() for path in (MASK, RGB)}
    try:
        for arm, revisions in ARMS.items():
            if args.probe and arm not in "CD":
                continue
            for path, revision in zip((MASK, RGB), revisions):
                (ROOT / path).write_bytes(git("show", f"{revision}:{path}"))
            name = f"probe-{arm}" if args.probe else arm
            if args.probe:
                instrument()
            build(directory, directory / f"build-{name}.log")
            shutil.copyfile(directory / "libexreader.dll", bins / f"{name}.dll")
            print(f"Built {name}", flush=True)
    finally:
        for path, content in original.items():
            (ROOT / path).write_bytes(content)


if __name__ == "__main__":
    main()
