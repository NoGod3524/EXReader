"""Actual PNG controls for reader image replay; synthetic pixels are not device evidence."""
import copy
import hashlib
import struct
import tempfile
import unittest
from pathlib import Path

from PIL import Image
import reader_android as R


BOX=(4,3,14,10)
LABELS={"page_label":"p.1 · 1.0 MiB · 7 ms","font_label":"Size 24","book_title":"Sample.epub"}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def bounds(box):
    left,top,right,bottom=box
    return dict(left=left,top=top,right=right,bottom=bottom,width=right-left,height=bottom-top)


def java_argb_summary(image):
    # Independent integer packing: Android Bitmap.getPixels returns 0xAARRGGBB;
    # the helper writes each integer most-significant byte first, in row order.
    colors=[(a<<24)|(r<<16)|(g<<8)|b for r,g,b,a in image.convert("RGBA").getdata()]
    encoded=b"".join(struct.pack(">I",color) for color in colors)
    return dict(algorithm="argb8888-be-v1",sha256=hashlib.sha256(encoded).hexdigest(),
                distinct_at_least_two=len(set(colors))>1,min_argb=min(colors),max_argb=max(colors),pixels=len(colors))


class PngFixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="exreader-f08-reader-images-")
        self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        (self.root/"ui/shots").mkdir(parents=True)

    def state(self,name,variant=0,box=BOX,uniform=False):
        screen=Image.new("RGBA",(24,18),(17,29,43,255))
        # Non-reader background is different from every ROI, so a real re-crop matters.
        screen.putpixel((0,0),(211,37,59,255))
        crop=Image.new("RGBA",(box[2]-box[0],box[3]-box[1]))
        crop.putdata([(0,0,0,255) if uniform else
                      ((x*17+y*11+variant*31)%256,(x*7+y*23+variant*47)%256,(x*29+y*3+variant*61)%256,255)
                      for y in range(crop.height) for x in range(crop.width)])
        screen.paste(crop,(box[0],box[1]))
        full_path=Path("shots")/(name+".png");crop_path=Path("shots")/(name+"-reader.png")
        full_file=self.root/"ui"/full_path;crop_file=self.root/"ui"/crop_path
        screen.save(full_file);crop.save(crop_file)
        view=dict(bounds=bounds(box),visible=True,enabled=True,directional_pan_action_ids=[])
        post={**LABELS,"reader_view":copy.deepcopy(view)}
        image=dict(status="captured",screenshot_captured=True,screenshot_path=full_path.as_posix(),
                   screenshot_sha256=sha(full_file),screenshot_bytes=full_file.stat().st_size,
                   screenshot_width=screen.width,screenshot_height=screen.height,
                   crop_path=crop_path.as_posix(),crop_sha256=sha(crop_file),crop_bytes=crop_file.stat().st_size,
                   bounds=bounds(box),bounds_after_capture=bounds(box),width=crop.width,height=crop.height,
                   capture_started_elapsed_ns=100,capture_finished_elapsed_ns=200,pixel_summary=java_argb_summary(crop))
        return {**LABELS,"reader_view":view,"public_after_capture":post,"reader_image":image}

    def verify(self,value,required=True):return R.verified_image(self.root,value,required)

    def rejects(self,value,required=True):
        with self.assertRaises((ValueError,FileNotFoundError)):self.verify(value,required)

    def rewrite_crop(self,value,crop):
        image=value["reader_image"];path=self.root/"ui"/image["crop_path"];crop.save(path)
        image.update(crop_sha256=sha(path),crop_bytes=path.stat().st_size,
                     width=crop.width,height=crop.height,pixel_summary=java_argb_summary(crop))


class ReaderImages(PngFixture):
    def test_real_png_recrop_and_java_argb_summary(self):
        state=self.state("valid");result=self.verify(state)
        self.assertEqual(result["bounds"],list(BOX))
        self.assertEqual(result["pixel_sha256"],state["reader_image"]["pixel_summary"]["sha256"])
        self.assertEqual(result["capture_finished_elapsed_ns"],200)

    def test_argb_order_uses_known_integer_bytes_not_rgba(self):
        state=self.state("channels");image=state["reader_image"]
        pixels=Image.new("RGBA",(2,1));pixels.putdata([(16,32,48,255),(64,80,96,128)])
        full=Image.new("RGBA",(24,18),(17,29,43,255));full.paste(pixels,(4,3))
        path=self.root/"ui"/image["screenshot_path"];full.save(path)
        image.update(screenshot_sha256=sha(path),screenshot_bytes=path.stat().st_size,
                     bounds=bounds((4,3,6,4)),bounds_after_capture=bounds((4,3,6,4)))
        state["reader_view"]["bounds"]=bounds((4,3,6,4));state["public_after_capture"]["reader_view"]["bounds"]=bounds((4,3,6,4))
        self.rewrite_crop(state,pixels)
        expected=hashlib.sha256(bytes.fromhex("ff10203080405060")).hexdigest()
        self.assertEqual(image["pixel_summary"]["sha256"],expected)
        self.assertEqual(self.verify(state)["pixel_sha256"],expected)
        image["pixel_summary"]["sha256"]=hashlib.sha256(bytes.fromhex("102030ff40506080")).hexdigest()
        self.rejects(state)

    def test_screenshot_sha_mismatch(self):
        value=self.state("full-sha");value["reader_image"]["screenshot_sha256"]="0"*64;self.rejects(value)

    def test_crop_sha_mismatch(self):
        value=self.state("crop-sha");value["reader_image"]["crop_sha256"]="0"*64;self.rejects(value)

    def test_authentic_wrong_crop_with_updated_hash_and_summary(self):
        value=self.state("wrong-crop");path=self.root/"ui"/value["reader_image"]["crop_path"]
        with Image.open(path) as raw:crop=raw.convert("RGBA")
        crop.putpixel((0,0),(255,254,253,255));self.rewrite_crop(value,crop);self.rejects(value)

    def test_forged_recrop_outside_public_reader_is_rejected(self):
        value=self.state("wrong-region");image=value["reader_image"];wrong=(5,3,15,10)
        image["bounds"]=bounds(wrong);image["bounds_after_capture"]=bounds(wrong)
        with Image.open(self.root/"ui"/image["screenshot_path"]) as full:self.rewrite_crop(value,full.crop(wrong))
        self.rejects(value)

    def test_inconsistent_bounds_dimensions(self):
        value=self.state("bounds-dimensions")
        for item in (value["reader_image"]["bounds"],value["reader_image"]["bounds_after_capture"],
                     value["reader_view"]["bounds"],value["public_after_capture"]["reader_view"]["bounds"]):item["width"]+=1
        self.rejects(value)

    def test_out_of_screen_or_non_integer_bounds(self):
        for key,bad in (("left",-1),("right",25),("top",3.0),("bottom",True),("right",4)):
            with self.subTest(key=key,bad=bad):
                value=self.state("invalid-bounds-"+str(key)+str(bad));value["reader_image"]["bounds"][key]=bad;self.rejects(value)

    def test_bounds_change_during_capture(self):
        value=self.state("moving");value["reader_image"]["bounds_after_capture"]["left"]+=1;self.rejects(value)

    def test_public_after_capture_bounds_change(self):
        value=self.state("post-moving");value["public_after_capture"]["reader_view"]["bounds"]["left"]+=1;self.rejects(value)

    def test_public_reader_not_visible(self):
        value=self.state("hidden");value["reader_view"]["visible"]=False;self.rejects(value)

    def test_public_label_change_during_capture(self):
        for label in LABELS:
            with self.subTest(label=label):
                value=self.state("moving-"+label);value["public_after_capture"][label]+=" changed";self.rejects(value)

    def test_uniform_reader_is_rejected_despite_nonuniform_toolbar(self):
        value=self.state("blank",uniform=True)
        with Image.open(self.root/"ui"/value["reader_image"]["screenshot_path"]) as full:self.assertGreater(len(set(full.getdata())),1)
        self.rejects(value)

    def test_missing_full_or_crop_png(self):
        for field in ("screenshot_path","crop_path"):
            with self.subTest(field=field):
                value=self.state("missing-"+field);(self.root/"ui"/value["reader_image"][field]).unlink();self.rejects(value)

    def test_pixel_summary_tampering(self):
        for key,bad in (("algorithm","rgba8888"),("sha256","0"*64),("min_argb",-1),("max_argb",0),("pixels",69),("distinct_at_least_two",False)):
            with self.subTest(key=key):
                value=self.state("summary-"+key);value["reader_image"]["pixel_summary"][key]=bad;self.rejects(value)

    def test_missing_reader_only_allowed_when_not_required(self):
        value=self.state("optional");image=value["reader_image"];image["status"]="missing"
        for key in ("crop_path","crop_sha256","pixel_summary"):image.pop(key)
        self.assertIsNone(self.verify(value,False));self.rejects(value,True)

    def test_capture_clock_and_boolean_types(self):
        for key,bad in (("capture_started_elapsed_ns",-1),("capture_started_elapsed_ns",True),
                        ("capture_finished_elapsed_ns",199.5),("capture_finished_elapsed_ns",99),("screenshot_captured",1)):
            with self.subTest(key=key,bad=bad):
                value=self.state("clock-"+str(key)+str(bad));value["reader_image"][key]=bad;self.rejects(value)

    def test_image_path_traversal_is_rejected(self):
        for path in ("../outside.png","/tmp/outside.png","shots\\outside.png","C:/outside.png"):
            with self.subTest(path=path):
                value=self.state("unsafe");value["reader_image"]["screenshot_path"]=path;self.rejects(value)


class ImageEffects(PngFixture):
    def images(self):
        variants={"page_forward":(0,1),"page_backward":(1,0),"font_increase":(0,2),
                  "font_decrease":(2,0),"search_found_select":(0,3)}
        return {case:{side:self.verify(self.state(case+"-"+side,pixels))
                      for side,pixels in zip(("before","after"),values)} for case,values in variants.items()}

    def checks(self,images):return {row["check"]:row for row in R.image_effects(images)}

    def test_actual_png_page_font_and_search_changes_and_round_trips(self):
        result=R.image_effects(self.images());self.assertEqual(len(result),7)
        self.assertTrue(all(row["passed"] for row in result),result)

    def test_changed_labels_cannot_substitute_for_changed_pixels(self):
        for case,label,new in (("page_forward","page_label","p.2"),("font_increase","font_label","Size 28"),
                               ("search_found_select","page_label","p.3")):
            with self.subTest(case=case):
                images=self.images();state=self.state(case+"-same-pixels",0)
                state[label]=new;state["public_after_capture"][label]=new
                images[case]["after"]=self.verify(state)
                self.assertFalse(self.checks(images)[case+"_changes_visible_reader"]["passed"])

    def test_page_backward_must_restore_origin_pixels(self):
        images=self.images();images["page_backward"]["after"]=self.verify(self.state("wrong-page-origin",4))
        self.assertFalse(self.checks(images)["page_backward_restores_forward_origin"]["passed"])

    def test_font_decrease_must_restore_original_pixels(self):
        images=self.images();images["font_decrease"]["after"]=self.verify(self.state("wrong-font-origin",4))
        self.assertFalse(self.checks(images)["font_decrease_restores_original"]["passed"])

    def test_identical_pixels_at_different_bounds_do_not_prove_restoration(self):
        images=self.images();images["page_backward"]["after"]=self.verify(self.state("shifted-origin",0,(5,3,15,10)))
        self.assertEqual(images["page_backward"]["after"]["pixel_sha256"],images["page_forward"]["before"]["pixel_sha256"])
        result=self.checks(images)["page_backward_restores_forward_origin"]
        self.assertFalse(result["same_bounds"]);self.assertFalse(result["passed"])

    def test_different_pixels_at_different_bounds_do_not_prove_page_change(self):
        images=self.images();images["page_forward"]["after"]=self.verify(self.state("shifted-change",1,(5,3,15,10)))
        result=self.checks(images)["page_forward_changes_visible_reader"]
        self.assertFalse(result["same_bounds"]);self.assertFalse(result["passed"])

    def test_missing_image_cannot_prove_change_or_restoration(self):
        images=self.images();images["font_increase"]["before"]=None;result=self.checks(images)
        self.assertFalse(result["font_increase_changes_visible_reader"]["passed"])
        self.assertFalse(result["font_decrease_restores_original"]["passed"])


if __name__=="__main__":unittest.main()
