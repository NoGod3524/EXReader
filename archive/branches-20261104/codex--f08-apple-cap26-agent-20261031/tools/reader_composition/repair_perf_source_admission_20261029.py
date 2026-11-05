"""Actions-only admission of this bounded GTK sampler repair."""
import ast,json,os,subprocess
from pathlib import Path
assert os.environ.get("GITHUB_ACTIONS")=="true"
BASE="fd592cd97afc759df764de7face5d1e3b5ec87ee"
PATH="tests/reader_product_performance_handoff/sample_gtk_interactions.py"
ALLOWED={PATH,"tools/reader_composition/repair_perf_source_admission_20261029.py",
 ".github/workflows/repair-perf-scroll-20261029.yml",
 "docs/reader-total-progress/repair-perf-scroll-20261029.md"}
def git(*args):return subprocess.check_output(["git",*args],text=True).strip()
assert git("rev-parse","HEAD")==os.environ["GITHUB_SHA"]
assert set(git("diff","--name-only",BASE,"HEAD").splitlines())==ALLOWED
old=ast.parse(git("show",BASE+":"+PATH));new=ast.parse(Path(PATH).read_text())
def constants(tree):return {n.targets[0].id:ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ("SCROLLS","FONT_STEPS","BURST_TURNS")}
assert constants(old)==constants(new)==dict(SCROLLS=6,FONT_STEPS=3,BURST_TURNS=20)
def method(tree,name):
 cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="Interactions")
 return ast.dump(next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==name),include_attributes=False)
assert method(old,"effect_and_paint")==method(new,"effect_and_paint")
assert method(old,"scenario_reader")==method(new,"scenario_reader")
out=Path("build/perf-repair-admission");out.mkdir(parents=True,exist_ok=True)
(out/"source.json").write_text(json.dumps(dict(source=os.environ["GITHUB_SHA"],base=BASE,
 changed=sorted(ALLOWED),original_production_and_main_samplers_unchanged=True,
 original_scroll_font_turn_counts_unchanged=True,original_scroll_response_deadline=180,
 numeric_budget_accepted=False),indent=2)+"\n")
