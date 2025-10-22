"""
Task Completion Detector

Enhanced detection system for identifying when Claude Code completes specific tasks.
Supports pattern-based detection, task-specific indicators, and smart alert prioritization.
"""

import re
import logging
import time
from typing import Dict, List, Tuple, Optional
from enum import Enum
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """Types of tasks Claude Code commonly performs"""
    CODE_GENERATION = "code_generation"
    BUILD_PROCESS = "build"
    TEST_EXECUTION = "test"
    FILE_OPERATION = "file_operation"
    SEARCH_OPERATION = "search"
    ANALYSIS = "analysis"
    DEPLOYMENT = "deployment"
    DOCUMENTATION = "documentation"
    DEBUGGING = "debugging"
    REFACTORING = "refactoring"
    INSTALLATION = "installation"
    CONFIGURATION = "configuration"
    GENERAL = "general"


class AlertPriority(Enum):
    """Alert priority levels for notifications"""
    CRITICAL = 1  # Errors, failures requiring immediate attention
    HIGH = 2      # Task completion with issues or warnings
    NORMAL = 3    # Regular task completion
    LOW = 4       # Informational completions


@dataclass
class TaskCompletion:
    """Represents a detected task completion"""
    task_type: TaskType
    priority: AlertPriority
    message: str
    details: str
    timestamp: datetime
    confidence: float  # 0.0 to 1.0
    pattern_matched: str
    context: Optional[str] = None


class TaskCompletionDetector:
    """Enhanced detector for task completion patterns"""
    
    def __init__(self):
        # Task-specific completion patterns with priorities
        self.task_patterns: Dict[TaskType, List[Tuple[str, AlertPriority, float]]] = {
            TaskType.BUILD_PROCESS: [
                (r"Build succeeded", AlertPriority.NORMAL, 0.9),
                (r"Build completed successfully", AlertPriority.NORMAL, 0.9),
                (r"✓ Build completed", AlertPriority.NORMAL, 0.9),
                (r"Build failed", AlertPriority.CRITICAL, 0.95),
                (r"Build error", AlertPriority.CRITICAL, 0.95),
                (r"Compilation failed", AlertPriority.CRITICAL, 0.95),
                (r"webpack: Compiled successfully", AlertPriority.NORMAL, 0.9),
                (r"Bundle size:", AlertPriority.LOW, 0.7),
            ],
            
            TaskType.TEST_EXECUTION: [
                (r"All tests passed", AlertPriority.NORMAL, 0.95),
                (r"✓ \d+ test[s]? passed", AlertPriority.NORMAL, 0.9),
                (r"Tests: \d+ passed, \d+ total", AlertPriority.NORMAL, 0.9),
                (r"Test Suites:.*passed", AlertPriority.NORMAL, 0.9),
                (r"\d+ tests? passed in \d+\.\d+s", AlertPriority.NORMAL, 0.95),  # pytest output
                (r"\d+ test[s]? failed", AlertPriority.HIGH, 0.95),
                (r"FAIL", AlertPriority.HIGH, 0.8),
                (r"Error: Test failed", AlertPriority.CRITICAL, 0.95),
                (r"0 failures", AlertPriority.NORMAL, 0.85),
                (r"in \d+\.\d+s\s*$", AlertPriority.LOW, 0.6),  # Test duration
            ],
            
            TaskType.FILE_OPERATION: [
                (r"File created:", AlertPriority.LOW, 0.8),
                (r"File saved:", AlertPriority.LOW, 0.8),
                (r"File deleted:", AlertPriority.LOW, 0.8),
                (r"Successfully wrote to", AlertPriority.LOW, 0.85),
                (r"Changes applied to \d+ file[s]?", AlertPriority.NORMAL, 0.85),
                (r"Created \d+ file[s]?", AlertPriority.NORMAL, 0.85),
                (r"Modified \d+ file[s]?", AlertPriority.NORMAL, 0.85),
            ],
            
            TaskType.SEARCH_OPERATION: [
                (r"Found \d+ match(es)?", AlertPriority.LOW, 0.85),
                (r"Search completed", AlertPriority.LOW, 0.8),
                (r"No matches found", AlertPriority.LOW, 0.85),
                (r"\d+ file[s]? searched", AlertPriority.LOW, 0.7),
            ],
            
            TaskType.INSTALLATION: [
                (r"Successfully installed", AlertPriority.NORMAL, 0.9),
                (r"Packages installed successfully", AlertPriority.NORMAL, 0.9),
                (r"added \d+ package[s]?", AlertPriority.NORMAL, 0.85),
                (r"Installation failed", AlertPriority.CRITICAL, 0.95),
                (r"npm ERR!", AlertPriority.CRITICAL, 0.95),
                (r"Dependencies installed", AlertPriority.NORMAL, 0.85),
                (r"up to date", AlertPriority.LOW, 0.7),
            ],
            
            TaskType.DEPLOYMENT: [
                (r"Deployment successful", AlertPriority.HIGH, 0.95),
                (r"Deploy complete", AlertPriority.HIGH, 0.95),
                (r"Successfully deployed to", AlertPriority.HIGH, 0.95),
                (r"Deployment failed", AlertPriority.CRITICAL, 0.95),
                (r"Push successful", AlertPriority.NORMAL, 0.85),
                (r"Published to", AlertPriority.HIGH, 0.9),
            ],
            
            TaskType.DEBUGGING: [
                (r"Bug fixed", AlertPriority.HIGH, 0.85),
                (r"Issue resolved", AlertPriority.HIGH, 0.85),
                (r"Error fixed", AlertPriority.HIGH, 0.85),
                (r"Debugger attached", AlertPriority.LOW, 0.7),
                (r"Breakpoint hit", AlertPriority.LOW, 0.7),
            ],
            
            TaskType.CODE_GENERATION: [
                (r"Generated \d+ file[s]?", AlertPriority.NORMAL, 0.85),
                (r"Code generated successfully", AlertPriority.NORMAL, 0.9),
                (r"Created component", AlertPriority.NORMAL, 0.85),
                (r"Function created", AlertPriority.NORMAL, 0.8),
                (r"Class generated", AlertPriority.NORMAL, 0.8),
            ],
            
            TaskType.GENERAL: [
                (r"Done!", AlertPriority.NORMAL, 0.8),
                (r"Completed", AlertPriority.NORMAL, 0.8),
                (r"Finished", AlertPriority.NORMAL, 0.8),
                (r"Success", AlertPriority.NORMAL, 0.75),
                (r"✓", AlertPriority.LOW, 0.6),
                (r"✅", AlertPriority.LOW, 0.6),
                (r"Task completed", AlertPriority.NORMAL, 0.85),
                (r"Process completed", AlertPriority.NORMAL, 0.85),
                (r"Operation successful", AlertPriority.NORMAL, 0.85),
            ],
        }
        
        # Error patterns that always trigger high priority alerts
        self.error_patterns = [
            (r"Error:", AlertPriority.CRITICAL, 0.9),
            (r"Failed:", AlertPriority.CRITICAL, 0.9),
            (r"Exception:", AlertPriority.CRITICAL, 0.95),
            (r"FATAL:", AlertPriority.CRITICAL, 0.95),
            (r"Traceback", AlertPriority.CRITICAL, 0.9),
            (r"SyntaxError", AlertPriority.CRITICAL, 0.95),
            (r"TypeError", AlertPriority.CRITICAL, 0.95),
            (r"ImportError", AlertPriority.CRITICAL, 0.95),
            (r"Permission denied", AlertPriority.HIGH, 0.9),
            (r"Connection refused", AlertPriority.HIGH, 0.9),
            (r"Timeout", AlertPriority.HIGH, 0.85),
        ]
        
        # Success indicators that boost confidence
        self.success_boosters = [
            "successfully", "completed", "passed", "succeeded",
            "finished", "done", "ready", "available"
        ]
        
        # Context patterns for better understanding
        self.context_patterns = {
            "duration": r"(?:took |in |Time: )(\d+\.\d+)s",
            "count": r"(\d+) (file|test|package|item)[s]?",
            "percentage": r"(\d+(?:\.\d+)?)%",
            "size": r"(\d+(?:\.\d+)?)(KB|MB|GB)",
        }
        
        # Track recent detections to avoid duplicates
        self.recent_detections: List[Tuple[str, float]] = []
        self.detection_window = 30  # seconds
    
    def detect_completion(self, screen_content: str) -> Optional[TaskCompletion]:
        """
        Detect task completion from screen content
        
        Args:
            screen_content: Current screen content from tmux
            
        Returns:
            TaskCompletion if detected, None otherwise
        """
        if not screen_content:
            return None
        
        # Focus on recent content (last 20 lines)
        lines = screen_content.split('\n')
        recent_content = '\n'.join(lines[-20:])
        
        # Check for error patterns first (highest priority)
        for pattern, priority, confidence in self.error_patterns:
            if re.search(pattern, recent_content, re.IGNORECASE):
                return self._create_completion(
                    TaskType.GENERAL,
                    priority,
                    "Error Detected",
                    self._extract_error_details(recent_content, pattern),
                    confidence,
                    pattern,
                    recent_content
                )
        
        # Check task-specific patterns
        best_match = None
        highest_confidence = 0.0
        
        for task_type, patterns in self.task_patterns.items():
            for pattern, priority, base_confidence in patterns:
                match = re.search(pattern, recent_content, re.IGNORECASE)
                if match:
                    # Calculate adjusted confidence
                    confidence = self._calculate_confidence(
                        recent_content, pattern, base_confidence
                    )
                    
                    if confidence > highest_confidence:
                        highest_confidence = confidence
                        best_match = self._create_completion(
                            task_type,
                            priority,
                            self._generate_message(task_type, match.group()),
                            self._extract_details(recent_content, pattern),
                            confidence,
                            pattern,
                            recent_content
                        )
        
        # Check if this is a duplicate detection
        if best_match and not self._is_duplicate(best_match):
            self._record_detection(best_match)
            return best_match
        
        return None
    
    def _calculate_confidence(self, content: str, pattern: str, base_confidence: float) -> float:
        """
        Calculate adjusted confidence based on context
        
        Args:
            content: Screen content
            pattern: Matched pattern
            base_confidence: Base confidence score
            
        Returns:
            Adjusted confidence score
        """
        confidence = base_confidence
        
        # Boost confidence if success indicators are present
        for booster in self.success_boosters:
            if booster.lower() in content.lower():
                confidence = min(1.0, confidence + 0.05)
        
        # Reduce confidence if content is too short
        if len(content) < 50:
            confidence *= 0.8
        
        # Boost confidence for multiple pattern matches
        pattern_count = len(re.findall(pattern, content, re.IGNORECASE))
        if pattern_count > 1:
            confidence = min(1.0, confidence + 0.1 * (pattern_count - 1))
        
        return confidence
    
    def _generate_message(self, task_type: TaskType, matched_text: str) -> str:
        """
        Generate user-friendly message for task completion
        
        Args:
            task_type: Type of task completed
            matched_text: Text that matched the pattern
            
        Returns:
            User-friendly message
        """
        messages = {
            TaskType.BUILD_PROCESS: "Build Process Completed",
            TaskType.TEST_EXECUTION: "Test Execution Finished",
            TaskType.FILE_OPERATION: "File Operation Completed",
            TaskType.SEARCH_OPERATION: "Search Completed",
            TaskType.INSTALLATION: "Installation Finished",
            TaskType.DEPLOYMENT: "Deployment Completed",
            TaskType.DEBUGGING: "Debugging Session Updated",
            TaskType.CODE_GENERATION: "Code Generation Completed",
            TaskType.GENERAL: "Task Completed",
        }
        
        return messages.get(task_type, "Task Completed")
    
    def _extract_details(self, content: str, pattern: str) -> str:
        """
        Extract relevant details from content
        
        Args:
            content: Screen content
            pattern: Matched pattern
            
        Returns:
            Extracted details
        """
        details = []
        
        # Extract context information
        for context_name, context_pattern in self.context_patterns.items():
            match = re.search(context_pattern, content, re.IGNORECASE)
            if match:
                details.append(f"{context_name}: {match.group(1)}")
        
        # Extract the line containing the pattern
        for line in content.split('\n'):
            if re.search(pattern, line, re.IGNORECASE):
                details.append(f"Output: {line.strip()}")
                break
        
        return ' | '.join(details) if details else "No additional details"
    
    def _extract_error_details(self, content: str, pattern: str) -> str:
        """
        Extract error details from content
        
        Args:
            content: Screen content
            pattern: Error pattern
            
        Returns:
            Error details
        """
        lines = content.split('\n')
        error_lines = []
        
        for i, line in enumerate(lines):
            if re.search(pattern, line, re.IGNORECASE):
                # Include the error line and next 2 lines for context
                error_lines.append(line.strip())
                if i + 1 < len(lines):
                    error_lines.append(lines[i + 1].strip())
                if i + 2 < len(lines):
                    error_lines.append(lines[i + 2].strip())
                break
        
        return ' | '.join(error_lines) if error_lines else "Error detected"
    
    def _create_completion(
        self,
        task_type: TaskType,
        priority: AlertPriority,
        message: str,
        details: str,
        confidence: float,
        pattern: str,
        context: str
    ) -> TaskCompletion:
        """
        Create a TaskCompletion object
        
        Args:
            task_type: Type of task
            priority: Alert priority
            message: Completion message
            details: Additional details
            confidence: Detection confidence
            pattern: Pattern that matched
            context: Full context
            
        Returns:
            TaskCompletion object
        """
        return TaskCompletion(
            task_type=task_type,
            priority=priority,
            message=message,
            details=details,
            timestamp=datetime.now(),
            confidence=confidence,
            pattern_matched=pattern,
            context=context[:500] if context else None  # Limit context size
        )
    
    def _is_duplicate(self, completion: TaskCompletion) -> bool:
        """
        Check if this is a duplicate detection
        
        Args:
            completion: TaskCompletion to check
            
        Returns:
            True if duplicate, False otherwise
        """
        current_time = time.time()
        pattern_hash = f"{completion.task_type.value}:{completion.pattern_matched}"
        
        # Clean old detections
        self.recent_detections = [
            (p, t) for p, t in self.recent_detections
            if current_time - t < self.detection_window
        ]
        
        # Check for duplicate
        for recent_pattern, _ in self.recent_detections:
            if recent_pattern == pattern_hash:
                return True
        
        return False
    
    def _record_detection(self, completion: TaskCompletion):
        """
        Record a detection to prevent duplicates
        
        Args:
            completion: TaskCompletion that was detected
        """
        pattern_hash = f"{completion.task_type.value}:{completion.pattern_matched}"
        self.recent_detections.append((pattern_hash, time.time()))
    
    def get_priority_emoji(self, priority: AlertPriority) -> str:
        """
        Get emoji for alert priority
        
        Args:
            priority: Alert priority level
            
        Returns:
            Appropriate emoji
        """
        emojis = {
            AlertPriority.CRITICAL: "🚨",
            AlertPriority.HIGH: "⚠️",
            AlertPriority.NORMAL: "✅",
            AlertPriority.LOW: "ℹ️",
        }
        return emojis.get(priority, "📢")


# Global instance for easy import
task_detector = TaskCompletionDetector()
