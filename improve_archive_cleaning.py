#!/usr/bin/env python3
"""
Improve Archive Cleaning Function
=================================

This script adds a complete conversation cleaning function to workflow_manager.py.
"""

def generate_cleaning_function():
    return '''
    def _clean_conversation_content(self, raw_content: str) -> str:
        """Clean and structure conversation content for better readability"""
        import re
        
        # Remove excessive technical output and tool calls
        lines = raw_content.split('\\n')
        cleaned_lines = []
        
        skip_patterns = [
            r'<function_calls>.*?</function_calls>',
            r'<parameter.*?