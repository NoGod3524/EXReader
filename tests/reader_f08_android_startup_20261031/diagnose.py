"""Attribute existing startup work, without rerunning or accepting the UI frame budget."""
import json,sys,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tests/reader_f08_android_20261031"))
import lane as L
def verify(value,ident,slot):
    L.need(all(value.get(k)==v for k,v in ident.items()) and value["slot"]==slot,"diagnostic identity")
    L.need(value["api"]==34 and value["abi"]=="x86_64" and value["books"]==2202 and
           value["f08_accepted"] is False and value["filesystem_cache_cold"] is False,"diagnostic scope")
    rows=value["query_rows"]
    L.need(len(rows)==2202 and len({r["sdk_id"] for r in rows})==2202,"all original SDK IDs")
    for name in ("has_local","lookup","heads"):
        values=[r[name+"_ns"] for r in rows]
        L.need(all(type(v) is int and v>=0 for v in values) and sum(values)==value[name+"_wall_ns"],"query timing totals")
    cases=value["comparisons"]
    L.need([r["query"] for r in cases]==["selection","heads","heads","selection"] and
           all(r["verified_books"]==2202 and r["heads"]>=2202 and 0<r["cpu_ns"]<=r["wall_ns"]*2 for r in cases),"ABBA query coverage")
    keys=value["key_comparisons"]
    L.need([r["query"] for r in keys]==["lookup","local_key","local_key","lookup"] and
           all(r["verified_books"]==2202 and 0<r["cpu_ns"]<=r["wall_ns"]*2 for r in keys),"key ABBA coverage")
    L.need(value["bookstore_open_wall_ns"]>0 and value["bookstore_open_cpu_ns"]>0,"constructor timing")
    return {k:v for k,v in value.items() if k!="query_rows"}
def run():
    L.guard();out=L.OUT;ident=L.identity()
    L.command(["adb","install","-r","-t",out/"packages/app-debug.apk"])
    L.command(["adb","install","-r","-t",out/"packages/app-debug-androidTest.apk"])
    common=["-e","source_sha",ident["source_sha"],"-e","run_id",ident["run_id"],"-e","attempt",ident["attempt"]]
    seed=L.command(["adb","shell","am","instrument","-w","-r",*common,"-e","phase","seed-ui",
        "org.exreader.host.test/org.exreader.host.ShelfCatalogTest"],timeout=300)
    (out/"startup-seed.txt").write_bytes(seed)
    L.need(b"EXR_SHELF_SEEDED 2202" in seed and b"INSTRUMENTATION_CODE: -1" in seed,"original corpus seed")
    installed=out/"installed";installed.mkdir()
    paths=L.command(["adb","shell","pm","path","org.exreader.host"],text=True).splitlines()
    L.need(len(paths)==1 and paths[0].startswith("package:"),"installed package")
    L.command(["adb","pull",paths[0][8:],installed/"app-debug.apk"])
    L.need(L.sha(installed/"app-debug.apk")==L.sha(out/"packages/app-debug.apk"),"installed bytes")
    L.command(["adb","shell","am","force-stop","org.exreader.host"])
    L.command(["adb","install","-r","-t",out/"packages/startup-cost-androidTest.apk"])
    summary=[]
    for slot in range(3):
        L.command(["adb","shell","am","force-stop","org.exreader.host"])
        output=L.command(["adb","shell","am","instrument","-w","-r",*common,"-e","slot",str(slot),
            "org.exreader.host.test/org.exreader.host.StartupCostTest"],timeout=120)
        (out/f"startup-{slot}.txt").write_bytes(output)
        L.need(b"F08_STARTUP_COST_OK" in output and b"INSTRUMENTATION_CODE: -1" in output,"startup diagnostic")
        raw=L.command(["adb","shell","run-as","org.exreader.host","cat","files/f08-startup-cost.json"])
        (out/f"startup-{slot}.json").write_bytes(raw)
        summary.append(verify(json.loads(raw),ident,slot))
    L.save(out/"startup-summary.json",summary)
    print("F08_ANDROID_STARTUP_COST",json.dumps(summary),flush=True)
if __name__=="__main__":
    run()
    if len(sys.argv)>1 and sys.argv[1]=="full":
        L.need(L.command(["adb","shell","pm","clear","org.exreader.host"],text=True).strip()=="Success","fresh original UI cohort")
        L.sample()
