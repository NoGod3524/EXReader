#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Cloud-only inspection of already-retained pixels; grants no acceptance."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import zipfile

from PIL import Image, ImageChops, ImageDraw
from check_parallel_integration import fetch, require

RUN = 39889934254
SOURCE = "c6f0ba92321a284490a81a2bb355557803c17ec9"
ARTIFACT = 12474462154
DIGEST = "sha256:b677a592fa31171a758820d3beba732986419d8fc2af303e113e4e933da7f837"

require(os.environ.get("GITHUB_ACTIONS") == "true", "Diagnostic must run in Actions")
output = Path("build/reading-pixel-diagnostic")
output.mkdir(parents=True, exist_ok=False)
metadata = fetch("actions/artifacts/" + str(ARTIFACT))
require(metadata["digest"] == DIGEST and not metadata["expired"] and metadata["size_in_bytes"] > 0 and
        metadata["workflow_run"]["id"] == RUN and metadata["workflow_run"]["head_sha"] == SOURCE,
        "Pinned input artifact identity refused")
archive_path = Path("build/reading-pixel-input.zip")
with archive_path.open("wb") as stream:
    subprocess.run(["gh", "api", f"repos/{os.environ['GITHUB_REPOSITORY']}/actions/artifacts/{ARTIFACT}/zip"],
                   stdout=stream, check=True, timeout=120)
require("sha256:" + hashlib.sha256(archive_path.read_bytes()).hexdigest() == DIGEST,
        "Pinned archive digest differs")
report = {"accepted": False, "diagnostic_only": True, "input_run": RUN, "input_source": SOURCE,
          "input_artifact": ARTIFACT, "input_digest": DIGEST, "pages": [], "render_parity_granted": False}
with zipfile.ZipFile(archive_path) as archive:
    summary = json.loads(archive.read("reading-real/summary.json"))
    require(summary["source_sha"] == SOURCE and summary["run_id"] == str(RUN) and summary["run_attempt"] == "1",
            "Original report identity refused")
    references = [item for item in summary["references"] if item["case"] == "irs-w9"]
    require([item["page"] for item in references] == [0, 1, 2], "W9 reference plan differs")
    for item in references:
        pictures = []
        for key in ("native", "reference"):
            name = "reading-real/" + item[key]
            require(archive.getinfo(name).file_size <= 20 * 1024 * 1024, "Pixel member exceeds diagnostic bound")
            data = archive.read(name)
            require(hashlib.sha256(data).hexdigest() == item[key + "_identity"]["sha256"], "Pixel file hash differs")
            with Image.open(io.BytesIO(data)) as picture:
                pictures.append(picture.convert("L"))
        native, reference = pictures
        require(native.size == reference.size == (612, 792), "Pixel dimensions changed")
        difference = ImageChops.difference(native, reference)
        histogram = difference.histogram()
        error = sum(index * count for index, count in enumerate(histogram)) / (612 * 792 * 255)
        crop = (0, 0, 612, 520)
        sheet = Image.new("L", (1836, 548), 255)
        draw = ImageDraw.Draw(sheet)
        views = [native, reference, ImageChops.invert(difference.point(lambda x: min(255, x * 4)))]
        for column, (title, view) in enumerate(zip(("EXReader native", "Poppler reference", "Difference x4 (white = equal)"), views)):
            draw.text((column * 612 + 8, 8), title, fill=0)
            sheet.paste(view.crop(crop), (column * 612, 28))
        png = io.BytesIO()
        sheet.quantize(colors=32, dither=getattr(Image, "Dither", Image).NONE).save(png, format="PNG", optimize=True)
        data = png.getvalue()
        while len(data) > 200 * 1024 and sheet.width > 1000:
            sheet = sheet.resize((int(sheet.width * .85), int(sheet.height * .85)), getattr(Image, "Resampling", Image).LANCZOS)
            png = io.BytesIO()
            sheet.quantize(colors=32, dither=getattr(Image, "Dither", Image).NONE).save(png, format="PNG", optimize=True)
            data = png.getvalue()
        require(len(data) <= 200 * 1024, "Contact sheet exceeds log image bound")
        (output / f"w9-{item['page']}-top-contact.png").write_bytes(data)
        report["pages"].append({"page": item["page"], "crop": crop, "gray_normalized_mae": error,
                                "contact_png_bytes": len(data), "contact_sha256": hashlib.sha256(data).hexdigest(),
                                "contact_only_gray_levels": 32, "contact_size": sheet.size})
        if item["page"] == 0:
            print("PIXEL_CONTACT_PNG_BEGIN", flush=True)
            print(base64.b64encode(data).decode("ascii"), flush=True)
            print("PIXEL_CONTACT_PNG_END", flush=True)
archive_path.unlink()
(output / "diagnostic.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report), flush=True)
