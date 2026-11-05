#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Write the fixed expectations before any consumer renders a message."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from localization_fixtures import write_fixtures


def main():
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "localization-fixtures")
    write_fixtures(target)
    print(target)


if __name__ == "__main__":
    main()
