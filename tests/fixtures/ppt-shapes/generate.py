"""Generate the committed M2 .ppt fixtures with real PowerPoint COM.

Run on Windows with PowerPoint and pywin32, as for ppt-legacy/generate.py.
Office and pywin32 are generation tools only; the reader and tests use neither.
The manifest records coordinates and colors reported after reopening the .ppt.
"""
import hashlib
import json
from pathlib import Path

import pythoncom
import win32com.client


def colorref(rgb):
    return rgb[0] | rgb[1] << 8 | rgb[2] << 16


def rgb(color):
    return [color & 255, color >> 8 & 255, color >> 16 & 255]


def shape(slide, name, kind, bounds, fill, line=None, weight=1):
    x, y, width, height = bounds
    item = (slide.Shapes.AddLine(x, y, x + width, y + height) if kind == "line"
            else slide.Shapes.AddShape(9 if kind == "ellipse" else 1, x, y, width, height))
    item.Name = name
    if kind != "line":
        item.Fill.Visible = -1 if fill is not None else 0
        if fill is not None:
            item.Fill.Solid()
            item.Fill.ForeColor.RGB = colorref(fill)
    item.Line.Visible = -1 if line is not None else 0
    if line is not None:
        item.Line.ForeColor.RGB = colorref(line)
        item.Line.Weight = weight
    return item


def report(item, group=None):
    if item.Type == 6:  # msoGroup
        children = []
        for i in range(1, item.GroupItems.Count + 1):
            children.extend(report(item.GroupItems.Item(i), item.Name))
        return children
    line = item.Type == 9  # msoLine
    return [{"name": item.Name,
             "kind": "line" if line else "ellipse" if item.AutoShapeType == 9 else "rect",
             "bbox_pt": [float(item.Left), float(item.Top), float(item.Width), float(item.Height)],
             "rgb": None if line or not item.Fill.Visible else rgb(item.Fill.ForeColor.RGB),
             "colorref": None if line or not item.Fill.Visible else f"0x{item.Fill.ForeColor.RGB & 0xffffff:08X}",
             "line_rgb": rgb(item.Line.ForeColor.RGB) if item.Line.Visible else None,
             "line_width_pt": float(item.Line.Weight) if item.Line.Visible else 0,
             "group": group}]


def main():
    directory = Path(__file__).resolve().parent
    pythoncom.CoInitialize()
    app = win32com.client.DispatchEx("PowerPoint.Application")
    fixtures = []
    red, blue, green = (255, 0, 0), (0, 0, 255), (0, 255, 0)
    cases = [("red-rect", 720, 540), ("blue-circle", 720, 540),
             ("overlap", 720, 540), ("group", 720, 540),
             ("standard", 720, 540), ("wide", 960, 540)]
    try:
        app.DisplayAlerts = 1  # ppAlertsNone
        for name, width, height in cases:
            path = directory / f"{name}.ppt"
            presentation = app.Presentations.Add(0)  # WithWindow=msoFalse
            try:
                presentation.PageSetup.SlideWidth = width
                presentation.PageSetup.SlideHeight = height
                slide = presentation.Slides.Add(1, 12)  # ppLayoutBlank
                slide.FollowMasterBackground = 0
                slide.Background.Fill.Solid()
                slide.Background.Fill.ForeColor.RGB = colorref((255, 255, 255))
                samples = []
                if name == "red-rect":
                    shape(slide, "red", "rect", (72, 72, 144, 108), red)
                    samples = [("red-center", (144, 126), red)]
                elif name == "blue-circle":
                    shape(slide, "blue", "ellipse", (100, 100, 144, 144), blue)
                    samples = [("blue-center", (172, 172), blue),
                               ("ellipse-corner", (104, 104), (255, 255, 255))]
                elif name == "overlap":
                    shape(slide, "red-back", "rect", (72, 72, 180, 144), red)
                    shape(slide, "green-front", "rect", (162, 126, 180, 144), green)
                    samples = [("red-only", (100, 100), red),
                               ("overlap-green", (200, 160), green),
                               ("green-only", (300, 240), green)]
                elif name == "group":
                    shape(slide, "group-red", "rect", (40, 30, 80, 60), red)
                    shape(slide, "group-blue", "rect", (140, 90, 60, 40), blue)
                    group = slide.Shapes.Range(["group-red", "group-blue"]).Group()
                    group.Name = "scaled-group"
                    group.LockAspectRatio = 0
                    group.Left, group.Top = 180, 135
                    group.Width, group.Height = 360, 200
                else:
                    shape(slide, "asymmetric-color", "rect" if name == "standard" else "ellipse",
                          (72, 72, 180, 144), (17, 83, 211))
                    shape(slide, "green-line", "line", (72, 300, 216, 0), None, green, 6)
                    shape(slide, "unfilled", "rect", (400, 72, 144, 108), None, red, 4)
                    samples = [("asymmetric-color", (162, 144), (17, 83, 211)),
                               ("green-line", (180, 300), green),
                               ("unfilled-center", (472, 126), (255, 255, 255))]
                presentation.SaveAs(str(path), 1)  # ppSaveAsPresentation
            finally:
                presentation.Close()
            saved = app.Presentations.Open(str(path), -1, 0, 0)
            try:
                slide = saved.Slides.Item(1)
                shapes = []
                groups = []
                for i in range(1, slide.Shapes.Count + 1):
                    item = slide.Shapes.Item(i)
                    shapes.extend(report(item))
                    if item.Type == 6:
                        groups.append({"name": item.Name, "bbox_pt": [float(item.Left), float(item.Top),
                                       float(item.Width), float(item.Height)]})
                if name == "group":
                    samples = [(item["name"] + "-center",
                                (item["bbox_pt"][0] + item["bbox_pt"][2] / 2,
                                 item["bbox_pt"][1] + item["bbox_pt"][3] / 2),
                                item["rgb"]) for item in shapes]
                reference = f"{name}-powerpoint.png"
                slide.Export(str(directory / reference), "PNG", width, height)
                fixtures.append({"file": path.name, "pages": saved.Slides.Count,
                                 "width_pt": float(saved.PageSetup.SlideWidth),
                                 "height_pt": float(saved.PageSetup.SlideHeight),
                                 "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                 "reference_png": reference, "shapes": shapes, "groups": groups,
                                 "samples": [{"name": label, "xy_pt": list(xy), "rgb": list(color)}
                                             for label, xy, color in samples]})
            finally:
                saved.Close()
        manifest = {"generator": "PowerPoint COM SaveAs(format=1), reopened COM coordinates/colors",
                    "version": app.Version, "reference_scale": "1 pixel per point",
                    "fixtures": fixtures}
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(manifest, indent=2))
    finally:
        app.Quit()
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    main()
