"""Automatic Terminal Health Monitoring System"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Set, Optional
from dataclasses import dataclass, field

from ..utils.terminal_health import TerminalHealthChecker, TerminalRecovery, TerminalHealth
from ..session_manager import SessionManager
from ..telegram.notifier import SmartNotifier
from ..config import ClaudeOpsConfig

logger = logging.getLogger(__name__)


@dataclass
class MonitoringStats:
    """Statistics for terminal monitoring"""
    total_checks: int = 0
    issues_detected: int = 0
    successful_recoveries: int = 0
    failed_recoveries: int = 0
    last_check_time: Optional[datetime] = None
    unhealthy_sessions: Set[str] = field(default_factory=set)


class TerminalHealthMonitor:
    """Automatic terminal health monitoring and recovery"""
    
    def __init__(self, config: ClaudeOpsConfig):
        self.config = config
        self.checker = TerminalHealthChecker()
        self.session_manager = SessionManager()
        self.notifier = SmartNotifier(config)
        
        # Configuration
        self.check_interval = 30  # seconds
        self.recovery_threshold = 2  # consecutive failures before auto-recovery
        self.auto_recovery_enabled = True
        
        # State tracking
        self.stats = MonitoringStats()
        self.session_failures: Dict[str, int] = {}  # session -> consecutive failure count
        self.last_recovery_attempt: Dict[str, datetime] = {}  # session -> last attempt time
        self.recovery_cooldown = timedelta(minutes=5)  # minimum time between recoveries
        
        # Monitor loop control
        self.running = False
        self.monitor_task = None
        
    def get_monitored_sessions(self) -> list[str]:
        """Get list of Claude sessions to monitor"""
        try:
            sessions = self.session_manager.get_all_claude_sessions()
            # Filter only Claude Code sessions
            claude_sessions = [s for s in sessions if s.startswith('claude_')]
            return claude_sessions
        except Exception as e:
            logger.error(f"Failed to get sessions: {e}")
            return []
    
    def should_auto_recover(self, session_name: str) -> bool:
        """Check if automatic recovery should be attempted"""
        if not self.auto_recovery_enabled:
            return False
            
        # Check failure count threshold
        failure_count = self.session_failures.get(session_name, 0)
        if failure_count < self.recovery_threshold:
            return False
            
        # Check cooldown period
        last_attempt = self.last_recovery_attempt.get(session_name)
        if last_attempt:
            if datetime.now() - last_attempt < self.recovery_cooldown:
                logger.info(f"Recovery cooldown active for {session_name}")
                return False
                
        return True
    
    async def check_session_health(self, session_name: str) -> TerminalHealth:
        """Check health of a single session"""
        try:
            health = self.checker.check_health(session_name)
            self.stats.total_checks += 1
            self.stats.last_check_time = datetime.now()
            
            if health.is_healthy:
                # Reset failure count on successful check
                if session_name in self.session_failures:
                    del self.session_failures[session_name]
                if session_name in self.stats.unhealthy_sessions:
                    self.stats.unhealthy_sessions.remove(session_name)
            else:
                # Increment failure count
                self.session_failures[session_name] = self.session_failures.get(session_name, 0) + 1
                self.stats.issues_detected += 1
                self.stats.unhealthy_sessions.add(session_name)
                
                logger.warning(f"Terminal health issue detected in {session_name}: {health.issues}")
                
            return health
            
        except Exception as e:
            logger.error(f"Health check failed for {session_name}: {e}")
            # Return unhealthy status for exceptions
            return TerminalHealth(
                session_name=session_name,
                expected_width=165,
                expected_height=73,
                actual_width=None,
                actual_height=None,
                is_healthy=False,
                issues=[f"Health check error: {str(e)}"],
                screen_sample=""
            )
    
    async def attempt_recovery(self, session_name: str, health: TerminalHealth) -> bool:
        """Attempt to recover a session with terminal issues"""
        try:
            logger.info(f"Attempting recovery for {session_name}")
            
            # Send notification about recovery attempt
            try:
                display_name = session_name.replace('claude_', '')
                message = (
                    f"🔧 **자동 터미널 복구**\n\n"
                    f"📋 **세션**: {display_name}\n"
                    f"🚨 **문제**: {', '.join(health.issues)}\n"
                    f"🔄 **복구 진행 중...**"
                )
                self.notifier.send_manual_notification(
                    title="터미널 자동 복구",
                    content=message,
                    urgency="normal"
                )
            except Exception as e:
                logger.error(f"Failed to send recovery notification: {e}")
            
            # Attempt recovery
            result = TerminalRecovery.fix_terminal(session_name, force_respawn=False)
            
            # Update last recovery attempt time
            self.last_recovery_attempt[session_name] = datetime.now()
            
            if result['success']:
                self.stats.successful_recoveries += 1
                logger.info(f"Successfully recovered {session_name}")
                
                # Send success notification
                try:
                    recovery_method = result.get('recovery_method', 'unknown')
                    success_message = (
                        f"✅ **터미널 복구 완료**\n\n"
                        f"📋 **세션**: {display_name}\n"
                        f"🔧 **방법**: {recovery_method}\n"
                        f"📐 **크기**: {result['health'].actual_width}x{result['health'].actual_height}\n"
                        f"💡 **자동 복구 성공**"
                    )
                    self.notifier.send_manual_notification(
                        title="터미널 복구 성공",
                        content=success_message,
                        urgency="low"
                    )
                except Exception as e:
                    logger.error(f"Failed to send success notification: {e}")
                
                return True
            else:
                self.stats.failed_recoveries += 1
                logger.error(f"Failed to recover {session_name}: {result.get('message', 'Unknown error')}")
                
                # Send failure notification
                try:
                    failure_message = (
                        f"❌ **터미널 복구 실패**\n\n"
                        f"📋 **세션**: {display_name}\n"
                        f"🚨 **문제**: {', '.join(health.issues)}\n"
                        f"⚠️ **수동 복구 필요**\n\n"
                        f"🔧 `/fix_terminal --force` 명령을 사용하세요"
                    )
                    self.notifier.send_manual_notification(
                        title="터미널 복구 실패",
                        content=failure_message,
                        urgency="high"
                    )
                except Exception as e:
                    logger.error(f"Failed to send failure notification: {e}")
                
                return False
                
        except Exception as e:
            logger.error(f"Recovery attempt failed for {session_name}: {e}")
            self.stats.failed_recoveries += 1
            return False
    
    async def monitor_cycle(self):
        """Single monitoring cycle - check all sessions"""
        sessions = self.get_monitored_sessions()
        if not sessions:
            logger.debug("No sessions to monitor")
            return
            
        logger.debug(f"Monitoring {len(sessions)} sessions: {sessions}")
        
        for session_name in sessions:
            try:
                # Check session health
                health = await self.check_session_health(session_name)
                
                if not health.is_healthy:
                    logger.warning(f"Unhealthy session detected: {session_name}")
                    
                    # Check if auto-recovery should be attempted
                    if self.should_auto_recover(session_name):
                        logger.info(f"Auto-recovery triggered for {session_name}")
                        success = await self.attempt_recovery(session_name, health)
                        
                        if success:
                            # Reset failure count after successful recovery
                            if session_name in self.session_failures:
                                del self.session_failures[session_name]
                        else:
                            # Disable auto-recovery for this session temporarily
                            logger.warning(f"Auto-recovery failed for {session_name}, disabling temporarily")
                    else:
                        # Just log the issue for now
                        failure_count = self.session_failures.get(session_name, 0)
                        logger.info(f"Session {session_name} unhealthy (failures: {failure_count}/{self.recovery_threshold})")
                        
                        # Send warning notification on first failure
                        if failure_count == 1:
                            try:
                                display_name = session_name.replace('claude_', '')
                                warning_message = (
                                    f"⚠️ **터미널 문제 감지**\n\n"
                                    f"📋 **세션**: {display_name}\n"
                                    f"🚨 **문제**: {', '.join(health.issues)}\n"
                                    f"🔍 **모니터링 중...**\n\n"
                                    f"연속 {self.recovery_threshold}회 실패 시 자동 복구됩니다"
                                )
                                self.notifier.send_manual_notification(
                                    title="터미널 문제 감지",
                                    content=warning_message,
                                    urgency="low"
                                )
                            except Exception as e:
                                logger.error(f"Failed to send warning notification: {e}")
                
                # Small delay between sessions
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error monitoring session {session_name}: {e}")
                continue
    
    async def monitor_loop(self):
        """Main monitoring loop"""
        logger.info("Terminal health monitor started")
        
        while self.running:
            try:
                await self.monitor_cycle()
                
                # Wait for next cycle
                await asyncio.sleep(self.check_interval)
                
            except asyncio.CancelledError:
                logger.info("Monitor loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                await asyncio.sleep(self.check_interval)
        
        logger.info("Terminal health monitor stopped")
    
    async def start(self):
        """Start the monitoring system"""
        if self.running:
            logger.warning("Monitor already running")
            return
            
        self.running = True
        self.monitor_task = asyncio.create_task(self.monitor_loop())
        logger.info(f"Terminal health monitor started (interval: {self.check_interval}s)")
    
    async def stop(self):
        """Stop the monitoring system"""
        if not self.running:
            logger.warning("Monitor not running")
            return
            
        self.running = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
            self.monitor_task = None
            
        logger.info("Terminal health monitor stopped")
    
    def get_status(self) -> dict:
        """Get monitoring status and statistics"""
        return {
            'running': self.running,
            'check_interval': self.check_interval,
            'auto_recovery_enabled': self.auto_recovery_enabled,
            'recovery_threshold': self.recovery_threshold,
            'stats': {
                'total_checks': self.stats.total_checks,
                'issues_detected': self.stats.issues_detected,
                'successful_recoveries': self.stats.successful_recoveries,
                'failed_recoveries': self.stats.failed_recoveries,
                'last_check_time': self.stats.last_check_time.isoformat() if self.stats.last_check_time else None,
                'unhealthy_sessions': list(self.stats.unhealthy_sessions),
            },
            'session_failures': self.session_failures,
            'cooldown_active': {
                session: (datetime.now() - last_attempt < self.recovery_cooldown)
                for session, last_attempt in self.last_recovery_attempt.items()
            }
        }