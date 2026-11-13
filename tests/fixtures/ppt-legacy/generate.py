"""Generate real PowerPoint 97-2003 fixtures without displaying a window.

Run on Windows with PowerPoint and pywin32 installed. Neither is an engine
dependency. Tests consume the committed fixtures and never invoke Office.
"""
import hashlib
import json
from pathlib import Path

import pythoncom
import win32com.client


def main():
    directory = Path(__file__).resolve().parent
    pythoncom.CoInitialize()
    app = win32com.client.DispatchEx("PowerPoint.Application")
    results = []
    try:
        app.DisplayAlerts = 1  # ppAlertsNone
        for count in (1, 5, 20, 0):
            path = directory / f"slides-{count}.ppt"
            presentation = app.Presentations.Add(0)  # WithWindow=msoFalse
            try:
                presentation.PageSetup.SlideWidth = 720
                presentation.PageSetup.SlideHeight = 540
                for index in range(count):
                    presentation.Slides.Add(index + 1, 12)  # ppLayoutBlank
                presentation.SaveAs(str(path), 1)  # ppSaveAsPresentation
            finally:
                presentation.Close()
            # Reopen the serialized PPT and record PowerPoint's own report.
            saved = app.Presentations.Open(str(path), -1, 0, 0)
            try:
                results.append({"file": path.name, "pages": saved.Slides.Count,
                                "width_pt": saved.PageSetup.SlideWidth,
                                "height_pt": saved.PageSetup.SlideHeight,
                                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            finally:
                saved.Close()
        manifest = {"generator": "PowerPoint COM SaveAs(format=1)", "version": app.Version,
                    "fixtures": results}
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(manifest, indent=2))
    finally:
        app.Quit()
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    main()
