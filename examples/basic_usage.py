#!/usr/bin/env python3
"""
Basic usage example for the Claude Code project.
This demonstrates the fundamental functionality.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def run_basic_example():
    """Run a basic usage example."""
    print("🎯 Running basic usage example...")
    
    # TODO: Add your basic usage example here
    # Example:
    # from your_project.core.service import YourService
    # service = YourService()
    # result = service.process()
    # print(f"Result: {result}")
    
    print("✅ Basic example completed successfully")

if __name__ == "__main__":
    run_basic_example()
