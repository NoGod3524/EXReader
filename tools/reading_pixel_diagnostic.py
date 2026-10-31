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

RUN = int(os.environ.get("DIAGNOSTIC_RUN", "39889934254"))
SOURCE = os.environ.get("DIAGNOSTIC_SOURCE", "c6f0ba92321a284490a81a2bb355557803c17ec9")
ARTIFACT = int(os.environ.get("DIAGNOSTIC_ARTIFACT", "12474462154"))
DIGEST = os.environ.get("DIAGNOSTIC_DIGEST", "sha256:b677a592fa31171a758820d3beba732986419d8fc2af303e113e4e933da7f837")

require(os.environ.get("GITHUB_ACTIONS") == "true", "Diagnostic must run in Actions")
selected_page = int(os.environ.get("DIAGNOSTIC_PAGE", "0"))
selected_case = os.environ.get("DIAGNOSTIC_CASE", "irs-w9")
manifest = json.loads(Path("tools/reading_corpus/real-v1.json").read_text())
entry = next((item for item in manifest["files"] if item["id"] == selected_case and item["format"] == "PDF"), None)
if "DIAGNOSTIC_SLOT" in os.environ:
    slot = int(os.environ["DIAGNOSTIC_SLOT"])
    require(entry is not None and 0 <= slot < len(entry["selected_pages"]), "Invalid registered reference slot")
    selected_page = entry["selected_pages"][slot]
require(entry is not None and selected_page in entry["selected_pages"], "Choose a registered PDF reference page")
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
    require(summary["source_sha"] == SOURCE and summary["run_id"] == str(RUN) and
            summary["run_attempt"] == str(fetch("actions/runs/" + str(RUN))["run_attempt"]) and
            summary["corpus_manifest_sha256"] == hashlib.sha256(Path("tools/reading_corpus/real-v1.json").read_bytes()).hexdigest(),
            "Original report identity refused")
    references = [item for item in summary["references"] if item["case"] == selected_case]
    require([item["page"] for item in references] == entry["selected_pages"], "Registered reference plan differs")
    for item in references:
        if item["page"] != selected_page:
            continue
        pictures = []
        for key in ("native", "reference"):
            name = "reading-real/" + item[key]
            require(archive.getinfo(name).file_size <= 20 * 1024 * 1024, "Pixel member exceeds diagnostic bound")
            data = archive.read(name)
            require(hashlib.sha256(data).hexdigest() == item[key + "_identity"]["sha256"], "Pixel file hash differs")
            with Image.open(io.BytesIO(data)) as picture:
                pictures.append(picture.convert("RGB"))
        native, reference = pictures
        require(native.size == reference.size and 0 < native.width <= 4096 and 0 < native.height <= 4096,
                "Pixel dimensions differ or exceed inspection bound")
        difference = ImageChops.difference(native, reference)
        histogram = difference.histogram()
        error = sum((index % 256) * count for index, count in enumerate(histogram)) / (native.width * native.height * 3 * 255)
        crop = (0, min(140, native.height // 4), min(612, native.width), min(400, native.height))
        thumb_height = max(1, round(native.height * 384 / native.width))
        column_width = max(400, crop[2])
        detail_y = thumb_height + 56
        sheet = Image.new("RGB", (3 * column_width, detail_y + crop[3] - crop[1]), "white")
        draw = ImageDraw.Draw(sheet)
        views = [native, reference, ImageChops.invert(difference.point(lambda x: min(255, x * 4)))]
        for column, (title, view) in enumerate(zip(("EXReader native", "Poppler reference", "Difference x4 (white = equal)"), views)):
            draw.text((column * column_width + 8, 8), title, fill="black")
            sheet.paste(view.resize((384, thumb_height), getattr(Image, "Resampling", Image).LANCZOS),
                        (column * column_width + (column_width - 384) // 2, 28))
            draw.text((column * column_width + 8, detail_y - 16), "Detail: original rectangle " + str(crop), fill="black")
            sheet.paste(view.crop(crop), (column * column_width, detail_y))
        png = io.BytesIO()
        sheet.quantize(colors=128, dither=getattr(Image, "Dither", Image).NONE).save(png, format="PNG", optimize=True)
        data = png.getvalue()
        while len(data) > 200 * 1024 and sheet.width > 1000:
            sheet = sheet.resize((int(sheet.width * .85), int(sheet.height * .85)), getattr(Image, "Resampling", Image).LANCZOS)
            png = io.BytesIO()
            sheet.quantize(colors=128, dither=getattr(Image, "Dither", Image).NONE).save(png, format="PNG", optimize=True)
            data = png.getvalue()
        require(len(data) <= 200 * 1024, "Contact sheet exceeds log image bound")
        (output / f"{selected_case}-{item['page']}-contact.png").write_bytes(data)
        report["pages"].append({"case": selected_case, "page": item["page"], "crop": crop, "rgb_normalized_mae": error,
                                "native_sha256": item["native_identity"]["sha256"],
                                "reference_sha256": item["reference_identity"]["sha256"],
                                "contact_png_bytes": len(data), "contact_sha256": hashlib.sha256(data).hexdigest(),
                                "contact_palette_colors": 128, "contact_size": sheet.size})
        print("PIXEL_CONTACT_PNG_BEGIN", flush=True)
        print(base64.b64encode(data).decode("ascii"), flush=True)
        print("PIXEL_CONTACT_PNG_END", flush=True)
archive_path.unlink()
(output / "diagnostic.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report), flush=True)
