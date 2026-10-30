"""Actions-only exact native Toggle hit-area repair admission."""
import os,subprocess
from pathlib import Path
assert os.environ.get("GITHUB_ACTIONS")=="true"
BASE="343bb94eb6513beaf5b344e7828342f6602a3b7b"
PATH="examples/apple/HostViews.swift"
ALLOWED={PATH,"tools/reader_composition/repair_apple_org_admission_20261029.py",
 ".github/workflows/repair-apple-organization-20261029.yml",
 "docs/reader-total-progress/repair-apple-organization-20261029.md"}
def git(*args):return subprocess.check_output(["git",*args],text=True).strip()
assert git("rev-parse","HEAD")==os.environ["GITHUB_SHA"]
assert set(git("diff","--name-only",BASE,"HEAD").splitlines())==ALLOWED
old=subprocess.check_output(["git","show",BASE+":"+PATH],text=True)
anchor="            Toggle(\"显示已移除\", isOn: $removed)\n                .accessibilityIdentifier(\"organization.removed\")\n                .onChange(of: removed) { _ in selectedGroup = nil; edit = \"\"; refresh() }"
replacement="#if os(iOS)\n            HStack {\n                Text(\"显示已移除\").accessibilityHidden(true)\n                Spacer()\n                Toggle(\"显示已移除\", isOn: $removed)\n                    .labelsHidden()\n                    .fixedSize(horizontal: true, vertical: false)\n                    .accessibilityLabel(\"显示已移除\")\n                    .accessibilityIdentifier(\"organization.removed\")\n                    .onChange(of: removed) { _ in selectedGroup = nil; edit = \"\"; refresh() }\n            }\n#else\n            Toggle(\"显示已移除\", isOn: $removed)\n                .accessibilityIdentifier(\"organization.removed\")\n                .onChange(of: removed) { _ in selectedGroup = nil; edit = \"\"; refresh() }\n#endif"
assert old.count(anchor)==1 and Path(PATH).read_text()==old.replace(anchor,replacement,1)
subprocess.run(["git","diff","--exit-code",BASE,"HEAD","--","tests","src","include","cmake","CMakeLists.txt","bindings","tools/build_apple_product.py","tools/check_apple_product.py"],check=True)
print("Only the exact iOS native Toggle layout changed; original six cases, assertions and budgets are unchanged",flush=True)
