"""Use every original raw report judge with this explicit workflow identity."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reader_reviewed_composition'))
import check_artifacts

check_artifacts.WORKFLOW = '.github/workflows/reader-composition-341.yml'
raise SystemExit(check_artifacts.main())
