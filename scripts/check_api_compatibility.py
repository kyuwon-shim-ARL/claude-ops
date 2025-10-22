#!/usr/bin/env python3
"""
API Compatibility Checker for wait_time_tracker versions

This script compares v1 and v2 to ensure all used methods are available.
Run this before deploying changes to catch missing methods early.
"""

import re
import sys
import subprocess
from pathlib import Path
from typing import Set, Dict

# Color codes for terminal output
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def extract_methods(file_path: str) -> Set[str]:
    """Extract all public method names from a Python file"""
    methods = set()
    try:
        with open(file_path, 'r') as f:
            content = f.read()

        # Find all method definitions (exclude private methods starting with _)
        pattern = r'def\s+([a-zA-Z]\w+)\s*\([^)]*\):'
        matches = re.findall(pattern, content)
        methods = set(m for m in matches if not m.startswith('_'))

        return methods
    except Exception as e:
        print(f"{RED}Error reading {file_path}: {e}{RESET}")
        return set()

def find_method_usages(method_name: str, search_dir: str, exclude_file: str = None) -> list:
    """Find all usages of a method in the codebase"""
    try:
        result = subprocess.run(
            ['grep', '-r', f'{method_name}', search_dir, '--include=*.py'],
            capture_output=True,
            text=True,
            timeout=5
        )

        # Filter out the definition itself and imports
        usages = []
        for line in result.stdout.split('\n'):
            if line and method_name in line:
                # Skip definitions and imports
                if f'def {method_name}' not in line and 'import' not in line:
                    # Extract file and line content
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        file_path = parts[0].strip()
                        # Skip usages in the excluded file (self-references in v1)
                        if exclude_file and file_path == exclude_file:
                            continue
                        usages.append(file_path)

        return list(set(usages))  # Deduplicate
    except Exception:
        return []

def main():
    print(f"{BLUE}{'='*70}{RESET}")
    print(f"{BLUE}API Compatibility Checker - wait_time_tracker v1 vs v2{RESET}")
    print(f"{BLUE}{'='*70}{RESET}\n")

    v1_file = "claude_ctb/utils/wait_time_tracker.py"
    v2_file = "claude_ctb/utils/wait_time_tracker_v2.py"

    # Extract methods from both versions
    v1_methods = extract_methods(v1_file)
    v2_methods = extract_methods(v2_file)

    print(f"📊 v1 has {len(v1_methods)} public methods")
    print(f"📊 v2 has {len(v2_methods)} public methods\n")

    # Find methods only in v1
    only_v1 = v1_methods - v2_methods

    # Find methods only in v2
    only_v2 = v2_methods - v1_methods

    # Check if missing methods are actually used
    critical_issues = []
    warnings = []

    if only_v1:
        print(f"{YELLOW}⚠️  Methods in v1 but MISSING in v2:{RESET}")
        print("=" * 70)

        for method in sorted(only_v1):
            # Exclude self-references in v1 (internal calls don't matter)
            usages = find_method_usages(method, "claude_ctb/", exclude_file=v1_file)

            if usages:
                print(f"{RED}  ❌ {method}() - USED IN CODE!{RESET}")
                for usage in usages[:3]:  # Show first 3 usages
                    print(f"     └─ {usage}")
                if len(usages) > 3:
                    print(f"     └─ ... and {len(usages) - 3} more locations")
                critical_issues.append(method)
            else:
                print(f"{GREEN}  ✓  {method}() - not used (safe to skip){RESET}")
                warnings.append(method)
        print()

    if only_v2:
        print(f"{GREEN}✨ NEW methods in v2 (not in v1):{RESET}")
        print("=" * 70)
        for method in sorted(only_v2):
            print(f"  ✅ {method}()")
        print()

    # Summary
    common = v1_methods & v2_methods
    print(f"{BLUE}{'='*70}{RESET}")
    print(f"{GREEN}✓  {len(common)} methods are common to both versions{RESET}")

    if critical_issues:
        print(f"{RED}✗  {len(critical_issues)} CRITICAL issues found!{RESET}")
        print(f"{RED}   These methods are used in the code but missing in v2:{RESET}")
        for method in critical_issues:
            print(f"{RED}   - {method}(){RESET}")
        print(f"\n{RED}💥 COMPATIBILITY BROKEN - Fix these before deploying!{RESET}\n")
        return 1
    elif warnings:
        print(f"{YELLOW}⚠  {len(warnings)} methods missing but not used{RESET}")
        print(f"{GREEN}✓  No critical issues - safe to proceed{RESET}\n")
        return 0
    else:
        print(f"{GREEN}✓  Perfect compatibility - all APIs match!{RESET}\n")
        return 0

if __name__ == "__main__":
    sys.exit(main())
