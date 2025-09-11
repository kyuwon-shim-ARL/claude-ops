"""
Test suite for Claude-Dev-Kit compatibility updates
Tests the enhanced project_creator.py functionality
"""

import unittest
from unittest.mock import Mock, patch, MagicMock, call
from pathlib import Path
import subprocess
import tempfile
import shutil
import os

from claude_ops.project_creator import ProjectCreator


class TestClaudeDevKitCompatibility(unittest.TestCase):
    """Test Claude-Dev-Kit integration enhancements"""
    
    def setUp(self):
        """Set up test environment"""
        self.test_dir = tempfile.mkdtemp()
        self.project_name = "test_project"
        self.project_path = Path(self.test_dir) / self.project_name
        
    def tearDown(self):
        """Clean up test environment"""
        if Path(self.test_dir).exists():
            shutil.rmtree(self.test_dir)
    
    def test_creates_required_directories_before_remote_install(self):
        """Test that all required directories are created before remote installation"""
        creator = ProjectCreator(self.project_name, str(self.project_path))
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
            
            # This should create directories first, then run install
            creator._install_remote_claude_dev_kit()
            
            # Check that all required directories exist
            required_dirs = [
                self.project_path / "docs" / "development" / "guides",
                self.project_path / "docs" / "development" / "sessions",
                self.project_path / "docs" / "CURRENT",
                self.project_path / "docs" / "specs",
                self.project_path / "src" / self.project_name / "core",
                self.project_path / "src" / self.project_name / "models",
                self.project_path / "src" / self.project_name / "services",
                self.project_path / "tests",
                self.project_path / "scripts",
                self.project_path / "examples"
            ]
            
            for dir_path in required_dirs:
                self.assertTrue(
                    dir_path.exists(),
                    f"Required directory {dir_path} was not created"
                )
    
    def test_validates_installation_success(self):
        """Test that installation success is properly validated"""
        creator = ProjectCreator(self.project_name, str(self.project_path))
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
            
            # Create only partial structure (missing CLAUDE.md)
            (self.project_path / "src").mkdir(parents=True)
            
            result = creator._install_remote_claude_dev_kit()
            
            # Should detect incomplete installation
            self.assertFalse(
                result,
                "Installation validation should fail when CLAUDE.md is missing"
            )
    
    def test_comprehensive_local_fallback_structure(self):
        """Test that local fallback creates complete claude-dev-kit structure"""
        creator = ProjectCreator(self.project_name, str(self.project_path))
        
        # Run local fallback
        result = creator._install_local_fallback()
        
        self.assertTrue(result, "Local fallback should succeed")
        
        # Verify complete structure
        expected_structure = {
            "src": {
                self.project_name: {
                    "core": ["__init__.py"],
                    "models": ["__init__.py"],
                    "services": ["__init__.py"],
                    "__init__.py": None
                }
            },
            "docs": {
                "CURRENT": ["active-todos.md", "planning.md", "status.md"],
                "development": {
                    "sessions": [],
                    "guides": ["claude-code-workflow.md"]
                },
                "specs": []
            },
            "tests": ["__init__.py", "test_main.py"],
            "scripts": ["test_setup.py"],
            "examples": ["basic_usage.py"],
            "CLAUDE.md": None,
            ".gitignore": None,
            "main_app.py": None,
            "README.md": None
        }
        
        self._verify_structure(self.project_path, expected_structure)
    
    def test_handles_remote_installation_timeout_gracefully(self):
        """Test graceful handling of remote installation timeout"""
        creator = ProjectCreator(self.project_name, str(self.project_path))
        
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("cmd", 30)
            
            result = creator._install_remote_claude_dev_kit()
            
            self.assertFalse(result, "Should return False on timeout")
            
            # Should still create basic directories
            self.assertTrue(
                (self.project_path / "docs").exists(),
                "Should create basic structure even on timeout"
            )
    
    def test_handles_partial_remote_installation_failure(self):
        """Test recovery from partial remote installation failure"""
        creator = ProjectCreator(self.project_name, str(self.project_path))
        
        with patch('subprocess.run') as mock_run:
            # Simulate partial failure
            mock_run.return_value = Mock(
                returncode=1,
                stdout="Created some directories",
                stderr="Error: docs/development/guides/claude-code-workflow.md: No such file"
            )
            
            result = creator._install_remote_claude_dev_kit()
            
            # Should detect failure
            self.assertFalse(result, "Should detect partial installation failure")
            
            # But directories should still be created
            self.assertTrue(
                (self.project_path / "docs" / "development" / "guides").exists(),
                "Should create missing directories on partial failure"
            )
    
    def test_creates_proper_gitignore_content(self):
        """Test that proper .gitignore content is created"""
        creator = ProjectCreator(self.project_name, str(self.project_path))
        
        creator._install_local_fallback()
        
        gitignore_path = self.project_path / ".gitignore"
        self.assertTrue(gitignore_path.exists(), ".gitignore should be created")
        
        content = gitignore_path.read_text()
        
        # Check for essential patterns
        essential_patterns = [
            "__pycache__/",
            "*.py[cod]",
            ".venv/",
            ".env",
            "*.egg-info/",
            ".pytest_cache/",
            "node_modules/",
            ".DS_Store",
            "*.log",
            ".claude/",
            "CLAUDE.md"
        ]
        
        for pattern in essential_patterns:
            self.assertIn(
                pattern, content,
                f"Essential pattern '{pattern}' missing from .gitignore"
            )
    
    def test_installation_validation_checks_critical_files(self):
        """Test that installation validation checks for all critical files"""
        creator = ProjectCreator(self.project_name, str(self.project_path))
        
        # Create incomplete structure
        self.project_path.mkdir(parents=True)
        (self.project_path / "src").mkdir()
        
        # Should fail validation
        is_valid = creator._validate_installation()
        self.assertFalse(is_valid, "Should fail validation with incomplete structure")
        
        # Add critical files one by one
        (self.project_path / "CLAUDE.md").write_text("# Project")
        is_valid = creator._validate_installation()
        self.assertFalse(is_valid, "Should still fail without complete structure")
        
        # Create complete structure
        creator._install_local_fallback()
        is_valid = creator._validate_installation()
        self.assertTrue(is_valid, "Should pass validation with complete structure")
    
    def _verify_structure(self, base_path, structure):
        """Helper to verify directory structure recursively"""
        for name, content in structure.items():
            path = base_path / name
            
            if content is None:
                # It's a file
                self.assertTrue(path.exists(), f"File {path} should exist")
            elif isinstance(content, dict):
                # It's a directory with subdirectories/files
                self.assertTrue(path.is_dir(), f"Directory {path} should exist")
                self._verify_structure(path, content)
            elif isinstance(content, list):
                # It's a directory with a list of files
                self.assertTrue(path.is_dir(), f"Directory {path} should exist")
                for file_name in content:
                    file_path = path / file_name
                    self.assertTrue(file_path.exists(), f"File {file_path} should exist")


class TestProjectCreatorIntegration(unittest.TestCase):
    """Integration tests for complete project creation flow"""
    
    def setUp(self):
        """Set up test environment"""
        self.test_dir = tempfile.mkdtemp()
        self.project_name = "integration_test"
        self.project_path = Path(self.test_dir) / self.project_name
        
    def tearDown(self):
        """Clean up test environment"""
        if Path(self.test_dir).exists():
            shutil.rmtree(self.test_dir)
    
    @patch('subprocess.run')
    def test_complete_project_creation_with_fallback(self, mock_run):
        """Test complete project creation flow with fallback to local"""
        # Set up mock to handle different commands
        def side_effect_func(*args, **kwargs):
            # Extract the command
            if args and args[0]:
                cmd = args[0] if isinstance(args[0], list) else str(args[0])
                
                # Git commands should succeed
                if 'git' in str(cmd):
                    return Mock(returncode=0, stdout="", stderr="")
                # Remote installation should fail
                elif 'curl' in str(cmd):
                    return Mock(returncode=1, stderr="Installation failed")
                # tmux commands should succeed
                elif 'tmux' in str(cmd):
                    # has-session returns 1 if session doesn't exist
                    if 'has-session' in str(cmd):
                        return Mock(returncode=1, stdout="", stderr="")
                    else:
                        return Mock(returncode=0, stdout="", stderr="")
            return Mock(returncode=0, stdout="", stderr="")
        
        mock_run.side_effect = side_effect_func
        
        creator = ProjectCreator(self.project_name, str(self.project_path))
        result = creator.create_project(initialize_git=True, install_dev_kit=True)
        
        # Should succeed with fallback
        self.assertEqual(result["status"], "success")
        
        # Check complete structure exists (git directory won't exist due to mocking)
        self.assertTrue((self.project_path / "CLAUDE.md").exists())
        self.assertTrue((self.project_path / "src" / self.project_name).exists())
        self.assertTrue((self.project_path / "docs" / "development" / "guides").exists())
        self.assertTrue((self.project_path / ".gitignore").exists())


if __name__ == "__main__":
    unittest.main()