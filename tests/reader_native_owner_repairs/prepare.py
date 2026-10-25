"""New owner source layout for explicitly reused D12 native primitives."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT
SOURCE = os.environ['GITHUB_SHA']
OUT = ROOT / 'build/native-owner-windows'

