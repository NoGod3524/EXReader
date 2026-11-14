"""Generate M4 binary PPT text oracles with PowerPoint COM (generation only)."""
import hashlib
import json
from pathlib import Path
import sys

sys.stdout.reconfigure(encoding="utf-8")

import pythoncom
import win32com.client


def rgb(value):
    return [value & 255, value >> 8 & 255, value >> 16 & 255]


def main():
    directory = Path(__file__).resolve().parent
    pythoncom.CoInitialize()
    app = win32com.client.DispatchEx("PowerPoint.Application")
    fixtures = []
    cases = ["hello", "size12", "size24", "size48", "regular", "bold", "cjk",
             "align-l", "align-ctr", "align-r", "bullets", "dot", "wrap", "spacing", "runs", "scheme"]
    try:
        app.DisplayAlerts = 1
        for case in cases:
            path = directory / (case + ".ppt")
            deck = app.Presentations.Add(0)
            try:
                deck.PageSetup.SlideWidth, deck.PageSetup.SlideHeight = 720, 540
                slide = deck.Slides.Add(1, 12)
                slide.FollowMasterBackground = 0
                slide.Background.Fill.Solid()
                slide.Background.Fill.ForeColor.RGB = 0xFFFFFF
                item = slide.Shapes.AddTextbox(1, 40, 40, 400, 300)
                item.Name = case
                item.Fill.Visible, item.Line.Visible = 0, 0
                frame = item.TextFrame
                frame.AutoSize, frame.WordWrap, frame.VerticalAnchor = 0, -1, 1
                frame.MarginLeft = frame.MarginRight = frame.MarginTop = frame.MarginBottom = 10
                text = "Hello"
                if case in ("regular", "bold"):
                    text = "IIIIIIII"
                elif case == "cjk":
                    text = "中文测试"
                elif case == "bullets":
                    text = "Item\rItem\rItem"
                elif case == "dot":
                    text = "•"
                elif case == "wrap":
                    text = "word " * 40
                    item.Width, item.Height = 200, 440
                elif case == "spacing":
                    text = "Hello\rHello\rHello"
                elif case == "runs":
                    text = "RedGreenBlue"
                frame.TextRange.Text = text
                tr = frame.TextRange
                tr.Font.Name = "Arial"
                tr.Font.NameFarEast = "SimHei"
                tr.Font.Size = 18
                tr.Font.Bold = tr.Font.Italic = tr.Font.Underline = 0
                tr.Font.Color.RGB = 0
                tr.ParagraphFormat.Alignment = 1
                tr.ParagraphFormat.Bullet.Visible = 0
                tr.ParagraphFormat.SpaceBefore = tr.ParagraphFormat.SpaceAfter = 0
                if case == "hello":
                    tr.ParagraphFormat.Alignment = 2
                elif case.startswith("size"):
                    tr.Font.Size = int(case[4:])
                elif case in ("regular", "bold"):
                    tr.Font.Size, tr.Font.Bold = 48, (-1 if case == "bold" else 0)
                elif case == "cjk":
                    tr.Font.Size = 28
                elif case.startswith("align-"):
                    tr.ParagraphFormat.Alignment = {"align-l": 1, "align-ctr": 2, "align-r": 3}[case]
                    tr.Font.Size = 24
                elif case in ("bullets", "dot"):
                    tr.Font.Size = 24
                    if case == "bullets":
                        tr.ParagraphFormat.Bullet.Type = 1
                        tr.ParagraphFormat.Bullet.Character = 0x2022
                        tr.ParagraphFormat.Bullet.Font.Name = "Arial"
                        tr.ParagraphFormat.Bullet.RelativeSize = 1
                        tr.ParagraphFormat.Bullet.Visible = -1
                        frame.Ruler.Levels(1).FirstMargin = 0
                        frame.Ruler.Levels(1).LeftMargin = 30
                elif case == "spacing":
                    tr.ParagraphFormat.LineRuleWithin = 0
                    tr.ParagraphFormat.SpaceWithin = 40
                    tr.ParagraphFormat.SpaceAfter = 12
                elif case == "runs":
                    for start, length, color in ((1, 3, 0x0000FF), (4, 5, 0x00AA00), (9, 4, 0xFF0000)):
                        tr.Characters(start, length).Font.Color.RGB = color
                    tr.Characters(4, 5).Font.Bold = -1
                    tr.Characters(9, 4).Font.Size = 24
                elif case == "scheme":
                    deck.SlideMaster.Theme.ThemeColorScheme.Colors(1).RGB = 0x22170C
                    tr.Font.Color.ObjectThemeColor = 1
                deck.SaveAs(str(path), 1)
            finally:
                deck.Close()
            saved = app.Presentations.Open(str(path), -1, 0, 0)
            try:
                slide = saved.Slides.Item(1)
                item = slide.Shapes.Item(1)
                tr = item.TextFrame.TextRange
                reference = case + "-powerpoint.png"
                slide.Export(str(directory / reference), "PNG", 720, 540)
                fixtures.append({"case": case, "file": path.name,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "reference_png": reference, "text": tr.Text,
                    "bbox_pt": [float(item.Left), float(item.Top), float(item.Width), float(item.Height)],
                    "margins_pt": [float(getattr(item.TextFrame, "Margin" + side)) for side in ("Left", "Top", "Right", "Bottom")],
                    "font": tr.Font.Name, "font_far_east": tr.Font.NameFarEast,
                    "size_pt": float(tr.Font.Size), "bold": int(tr.Font.Bold),
                    "rgb": rgb(tr.Font.Color.RGB), "alignment": int(tr.ParagraphFormat.Alignment),
                    "bullet_character": int(tr.ParagraphFormat.Bullet.Character),
                    "bullet_visible": int(tr.ParagraphFormat.Bullet.Visible)})
            finally:
                saved.Close()
        manifest = {"generator": "PowerPoint COM SaveAs(format=1); reopened COM text oracle",
                    "version": app.Version, "fixtures": fixtures}
        (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    finally:
        app.Quit()
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    main()
