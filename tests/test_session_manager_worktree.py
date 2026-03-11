"""
Tests for worktree-aware session manager methods.
Covers: find_sessions_for_project, _resolve_worktree_parent, connect_to_project ordering.
"""

import unittest
from unittest.mock import patch, MagicMock

from claude_ctb.session_manager import SessionManager


class TestFindSessionsForProject(unittest.TestCase):
    """Test find_sessions_for_project with worktree path matching."""

    def setUp(self):
        self.manager = SessionManager()

    @patch.object(SessionManager, 'get_session_path')
    @patch.object(SessionManager, 'get_all_claude_sessions')
    def test_exact_match(self, mock_sessions, mock_path):
        """Session with exact project path should match."""
        mock_sessions.return_value = ['claude_myapp']
        mock_path.return_value = '/home/user/projects/myapp'

        result = self.manager.find_sessions_for_project('/home/user/projects/myapp')
        self.assertEqual(result, ['claude_myapp'])

    @patch.object(SessionManager, 'get_session_path')
    @patch.object(SessionManager, 'get_all_claude_sessions')
    def test_worktree_subdirectory_match(self, mock_sessions, mock_path):
        """Session in a worktree subdirectory should match parent project."""
        mock_sessions.return_value = ['claude_feature-auth']
        mock_path.return_value = '/home/user/projects/myapp/.claude/worktrees/feature-auth'

        result = self.manager.find_sessions_for_project('/home/user/projects/myapp')
        self.assertEqual(result, ['claude_feature-auth'])

    @patch.object(SessionManager, 'get_session_path')
    @patch.object(SessionManager, 'get_all_claude_sessions')
    def test_prefix_but_different_project_no_match(self, mock_sessions, mock_path):
        """Project 'foo' should NOT match session in 'foobar'."""
        mock_sessions.return_value = ['claude_foobar']
        mock_path.return_value = '/home/user/projects/foobar'

        result = self.manager.find_sessions_for_project('/home/user/projects/foo')
        self.assertEqual(result, [])

    @patch.object(SessionManager, 'get_session_path')
    @patch.object(SessionManager, 'get_all_claude_sessions')
    def test_multiple_sessions_mixed(self, mock_sessions, mock_path):
        """Should return both exact and worktree matches, exclude unrelated."""
        mock_sessions.return_value = ['claude_myapp', 'claude_feature-x', 'claude_other']
        mock_path.side_effect = [
            '/home/user/projects/myapp',
            '/home/user/projects/myapp/.claude/worktrees/feature-x',
            '/home/user/projects/other',
        ]

        result = self.manager.find_sessions_for_project('/home/user/projects/myapp')
        self.assertEqual(result, ['claude_myapp', 'claude_feature-x'])

    @patch.object(SessionManager, 'get_session_path')
    @patch.object(SessionManager, 'get_all_claude_sessions')
    def test_empty_session_path(self, mock_sessions, mock_path):
        """Session with empty path (tmux error) should not match."""
        mock_sessions.return_value = ['claude_broken']
        mock_path.return_value = ''

        result = self.manager.find_sessions_for_project('/home/user/projects/myapp')
        self.assertEqual(result, [])


class TestResolveWorktreeParent(unittest.TestCase):
    """Test _resolve_worktree_parent static method."""

    def test_worktree_path(self):
        path = '/home/user/projects/myapp/.claude/worktrees/feature-auth'
        self.assertEqual(
            SessionManager._resolve_worktree_parent(path),
            '/home/user/projects/myapp'
        )

    def test_normal_path(self):
        path = '/home/user/projects/myapp'
        self.assertEqual(
            SessionManager._resolve_worktree_parent(path),
            '/home/user/projects/myapp'
        )

    def test_nested_worktree_path(self):
        """Edge case: .claude/worktrees appears in path."""
        path = '/home/user/projects/deep/.claude/worktrees/wt1'
        self.assertEqual(
            SessionManager._resolve_worktree_parent(path),
            '/home/user/projects/deep'
        )


class TestConnectToProjectOrdering(unittest.TestCase):
    """Test connect_to_project picks most recently active session."""

    def setUp(self):
        self.manager = SessionManager()

    @patch('os.path.isdir', return_value=True)
    @patch.object(SessionManager, 'switch_session', return_value=True)
    @patch.object(SessionManager, 'find_sessions_for_project')
    def test_picks_first_session_most_recent(self, mock_find, mock_switch, mock_isdir):
        """Should pick first session (most recently active from sorted list)."""
        mock_find.return_value = ['claude_myapp', 'claude_myapp_wt_feat']

        result = self.manager.connect_to_project('/home/user/projects/myapp')

        self.assertEqual(result['session_name'], 'claude_myapp')
        mock_switch.assert_called_once_with('claude_myapp')


if __name__ == '__main__':
    unittest.main()
