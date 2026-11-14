"""Regenerate M3 binary PowerPoint oracles on Windows (Office + pywin32).

These are generation tools only; the committed-fixture tests use the stdlib.
"""
import hashlib
import json
from pathlib import Path
import struct
import zlib

import pythoncom
import win32com.client


def png():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 100, 50, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress((b"\0" + b"\0\xff\0" * 100) * 50)) + chunk(b"IEND", b""))


def rgb(value):
    return [value & 255, value >> 8 & 255, value >> 16 & 255]


def main():
    directory = Path(__file__).resolve().parent
    directory.mkdir(exist_ok=True)
    source = directory / "green-100x50.png"
    source.write_bytes(png())
    pythoncom.CoInitialize()
    app = win32com.client.DispatchEx("PowerPoint.Application")
    fixtures = []
    try:
        app.DisplayAlerts = 1
        for case in ("png", "scale", "gradient", "theme"):
            path = directory / (case + ".ppt")
            deck = app.Presentations.Add(0)
            try:
                deck.PageSetup.SlideWidth, deck.PageSetup.SlideHeight = 720, 540
                slide = deck.Slides.Add(1, 12)
                slide.FollowMasterBackground = 0
                slide.Background.Fill.Solid()
                slide.Background.Fill.ForeColor.RGB = 0xFFFFFF
                if case in ("png", "scale"):
                    width = 100 if case == "png" else 400
                    item = slide.Shapes.AddPicture(str(source), 0, -1, 80, 80, width, 50)
                else:
                    item = slide.Shapes.AddShape(1, 80, 80, 400, 100)
                    item.Line.Visible = 0
                    item.Fill.Visible = -1
                    if case == "gradient":
                        item.Fill.TwoColorGradient(1, 1)
                        item.Fill.ForeColor.RGB = 0x0000FF
                        item.Fill.BackColor.RGB = 0xFF0000
                        item.Fill.GradientAngle = 0
                    else:
                        item.Delete()
                        entries = [("accent1", 5, [17, 83, 211]), ("accent2", 6, [19, 123, 41]),
                                   ("accent3", 7, [241, 97, 23]), ("accent4", 8, [91, 31, 201]),
                                   ("accent5", 9, [201, 41, 153]), ("accent6", 10, [7, 177, 221]),
                                   ("background", 2, [233, 241, 249]), ("text", 1, [12, 23, 34])]
                        for index, (label, theme, color) in enumerate(entries):
                            deck.SlideMaster.Theme.ThemeColorScheme.Colors(theme).RGB = color[0] | color[1] << 8 | color[2] << 16
                            item = slide.Shapes.AddShape(1, 80 + (index % 2) * 250, 80 + (index // 2) * 100, 200, 70)
                            item.Name = label
                            item.Line.Visible = 0
                            item.Fill.Solid()
                            item.Fill.ForeColor.ObjectThemeColor = theme
                if case != "theme":
                    item.Name = case
                deck.SaveAs(str(path), 1)
            finally:
                deck.Close()
            saved = app.Presentations.Open(str(path), -1, 0, 0)
            try:
                slide, item = saved.Slides.Item(1), saved.Slides.Item(1).Shapes.Item(1)
                reference = case + "-powerpoint.png"
                slide.Export(str(directory / reference), "PNG", 720, 540)
                fixture = {"case": case, "file": path.name,
                           "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                           "reference_png": reference, "bbox_pt": [float(item.Left), float(item.Top),
                            float(item.Width), float(item.Height)]}
                if case == "theme":
                    fixture["shapes"] = []
                    for index in range(1, slide.Shapes.Count + 1):
                        shape = slide.Shapes.Item(index)
                        fixture["shapes"].append({"name": shape.Name,
                            "bbox_pt": [float(shape.Left), float(shape.Top), float(shape.Width), float(shape.Height)],
                            "rgb": rgb(shape.Fill.ForeColor.RGB), "object_theme_color": shape.Fill.ForeColor.ObjectThemeColor,
                            "master_rgb": rgb(saved.SlideMaster.Theme.ThemeColorScheme.Colors(shape.Fill.ForeColor.ObjectThemeColor).RGB)})
                if case == "gradient":
                    fixture["stops"] = [{"rgb": rgb(item.Fill.GradientStops(i).Color.RGB),
                                         "position": item.Fill.GradientStops(i).Position}
                                        for i in range(1, item.Fill.GradientStops.Count + 1)]
                    fixture["angle"] = item.Fill.GradientAngle
                fixtures.append(fixture)
            finally:
                saved.Close()
        manifest = {"generator": "PowerPoint COM SaveAs(format=1); reopened COM oracle",
                    "version": app.Version, "fixtures": fixtures}
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(manifest, indent=2))
    finally:
        app.Quit()
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    main()
