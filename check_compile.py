#!/usr/bin/env python3
"""Check all Python files for compilation errors."""

import py_compile
import sys
import os
from pathlib import Path

errors = []
success = []

# Get all Python files
files_to_check = []
files_to_check.append(Path('server.py'))

for root, dirs, filenames in os.walk('testing'):
    for filename in filenames:
        if filename.endswith('.py') and not filename.startswith('__'):
            filepath = Path(root) / filename
            files_to_check.append(filepath)

print(f"Checking {len(files_to_check)} Python files...\n")

for filepath in sorted(files_to_check):
    try:
        py_compile.compile(str(filepath), doraise=True)
        success.append(str(filepath))
        print(f"[PASS] {filepath}")
    except py_compile.PyCompileError as e:
        errors.append((str(filepath), str(e)))
        print(f"[FAIL] {filepath}")
        print(f"  Error: {e}\n")

print(f"\n{'='*60}")
print(f"Results: {len(success)} passed, {len(errors)} failed")
print(f"{'='*60}")

if errors:
    print("\nFailed files:")
    for filepath, error in errors:
        print(f"  - {filepath}")
    sys.exit(1)
else:
    print("\nAll files compiled successfully!")
    sys.exit(0)
