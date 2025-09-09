"""
TADD (Task-Aware Development & Delivery) Integration Module

This module provides comprehensive TADD methodology implementation for Claude-Ops,
including task management, document automation, PRD lifecycle, and session archiving.
"""

__version__ = "1.0.0"
__author__ = "Claude Code with TADD Methodology"

from .task_manager import TADDTaskManager
from .document_generator import TADDDocumentGenerator
from .prd_manager import TADDPRDManager
from .session_archiver import TADDSessionArchiver

__all__ = [
    "TADDTaskManager",
    "TADDDocumentGenerator", 
    "TADDPRDManager",
    "TADDSessionArchiver"
]