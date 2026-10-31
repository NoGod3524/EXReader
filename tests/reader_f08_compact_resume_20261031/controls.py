"""Regression checks for startup attribution; no performance samples."""
import copy
import json
import os
import adapter as A

def main():
    A.need(os.environ.get("GITHUB_ACTIONS")=="true","Actions only")
    state=dict(compact=1,compact_resume=7,book=0,books=50,reader_visible=0,
               busy=0,saving=0,shelf_loading=0,shelf_restoring=0,sequence=4)
    row=dict(schema=1,pid=42,requested_book=7,stage="continued",launch_start=100,
             wait_start=150,before_at=140,input_start=300,input_end=340,after_at=320,wait_end=350,
             deadline=600000150,window=88,active_window=88,window_pid=42,before=state,
             after=dict(state,book=7,reader_visible=1,sequence=5),
             control=dict(pid=42,name="Continue reading",role="push button",
                          states=dict(showing=True,sensitive=True,enabled=True),
                          bounds=dict(x=12,y=8,width=80,height=32)))
    A.verify(row)
    A.verify(dict(schema=1,pid=42,stage="shelf_unchanged",requested_book=0))
    negative=[]
    changes=[
        ("wrong_book",lambda r:r["before"].update(compact_resume=8)),
        ("already_reading",lambda r:r["before"].update(book=7,reader_visible=1)),
        ("empty_library",lambda r:r["before"].update(books=0)),
        ("restoring",lambda r:r["before"].update(shelf_restoring=1)),
        ("busy",lambda r:r["before"].update(busy=1)),
        ("wrong_pid",lambda r:r["control"].update(pid=43)),
        ("disabled",lambda r:r["control"]["states"].update(sensitive=False)),
        ("hidden",lambda r:r["control"]["states"].update(showing=False)),
        ("no_geometry",lambda r:r["control"]["bounds"].update(width=0)),
        ("wrong_window",lambda r:r.update(active_window=89)),
        ("pre_input_effect",lambda r:r.update(after_at=299)),
        ("wrong_effect_book",lambda r:r["after"].update(book=8)),
        ("stale_state",lambda r:r["after"].update(sequence=4)),
        ("expanded_deadline",lambda r:r.update(deadline=600000151)),
        ("late_success",lambda r:r.update(wait_end=600000151)),
    ]
    for name,change in changes:
        candidate=copy.deepcopy(row);change(candidate)
        try:A.verify(candidate)
        except A.O.SampleError:negative.append(name)
        else:raise AssertionError("accepted invalid "+name)
    for stamp in (10,11):
        try:A.remaining(10,stamp)
        except A.O.SampleError:negative.append("expired_"+str(stamp))
        else:raise AssertionError("deadline renewed")
    assert A.remaining(1000000,500000)==.5
    print("F08_COMPACT_CONTROLS",json.dumps(dict(positive=3,negative=negative,performance_samples=False)))
if __name__=="__main__":main()
