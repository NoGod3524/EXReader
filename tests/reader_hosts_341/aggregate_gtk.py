"""Retain every sealed GTK judge; select the exact new common production pin."""
from pathlib import Path
import sys

from guard_gtk import BASE
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'reader_gtk_341_final'))
import aggregate as sealed_gtk
import navigation_contract

# This is the verifier's expected production snapshot, never a runtime SDK,
# parser tag, record, request, selector, pixel or acceptance-result override.
navigation_contract.MERGED=BASE
sealed_gtk.main()
