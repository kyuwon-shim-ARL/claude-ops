"""
Hybrid Monitoring System
Combines Claude Code hooks (primary) with fallback polling (backup)
"""

import os
import time
import json
import logging
import threading
import subprocess
from pathlib import Path
from typing import Dict, Set, Optional
from datetime import datetime, timedelta

from ..config import ClaudeOpsConfig
from ..session_manager import session_manager
from ..utils.session_state import SessionStateAnalyzer, SessionState
from ..telegram.notifier import SmartNotifier
from ..hook_manager import HookManager

logger = logging.getLogger(__name__)


class HybridMonitor:
    """Hybrid monitoring system combining hooks and polling"""
    
    def __init__(self, config: Optional[ClaudeOpsConfig] = None):
        self.config = config or ClaudeOpsConfig()
        self.hook_manager = HookManager(self.config)
        self.notifier = SmartNotifier(self.config)
        self.state_analyzer = SessionStateAnalyzer()
        
        # Hybrid monitoring state
        self.running = False
        self.hook_mode_active = True
        self.fallback_active = False
        
        # Hook activity tracking
        self.last_hook_activity: Dict[str, datetime] = {}
        self.hook_timeout = timedelta(seconds=30)
        self.fallback_check_interval = 10  # seconds
        
        # Fallback polling state (simplified from multi_monitor)
        self.last_state: Dict[str, SessionState] = {}
        self.last_notification_time: Dict[str, float] = {}
        self.notification_cooldown = 30  # seconds
        
        # Performance metrics
        self.metrics = {
            "hook_triggers": 0,
            "fallback_triggers": 0,
            "notifications_sent": 0,
            "hook_failures": 0,
            "start_time": datetime.now()
        }
    
    def start_monitoring(self):
        """Start hybrid monitoring system"""
        try:
            # Setup hooks first
            if not self.hook_manager.setup_hooks():
                logger.warning("Hook setup failed, running in fallback-only mode")
                self.hook_mode_active = False
                self.fallback_active = True
            else:
                logger.info("✅ Hook system initialized")
                self.hook_mode_active = True
            
            # Start monitoring threads
            self.running = True
            
            # Hook activity monitor thread
            if self.hook_mode_active:
                hook_thread = threading.Thread(
                    target=self._monitor_hook_activity,
                    daemon=True,
                    name="hook-activity-monitor"
                )
                hook_thread.start()
            
            # Fallback polling thread
            fallback_thread = threading.Thread(
                target=self._fallback_monitor,
                daemon=True,
                name="fallback-monitor"
            )
            fallback_thread.start()
            
            # Metrics thread
            metrics_thread = threading.Thread(
                target=self._update_metrics,
                daemon=True,
                name="metrics-monitor"
            )
            metrics_thread.start()
            
            logger.info("🚀 Hybrid monitoring system started")
            
            # Main monitoring loop
            while self.running:
                try:
                    # Check system health
                    self._health_check()
                    time.sleep(5)
                    
                except KeyboardInterrupt:
                    logger.info("🛑 Hybrid monitoring stopped by user")
                    break
                except Exception as e:
                    logger.error(f"Error in main monitoring loop: {e}")
                    time.sleep(10)
        
        finally:
            self.running = False
            logger.info("🏁 Hybrid monitoring system stopped")
    
    def _monitor_hook_activity(self):
        """Monitor hook activity and detect failures"""
        while self.running and self.hook_mode_active:
            try:
                current_time = datetime.now()
                
                # Check for hook timeouts
                for session, last_activity in list(self.last_hook_activity.items()):
                    if current_time - last_activity > self.hook_timeout:
                        logger.warning(f"Hook timeout detected for {session}, activating fallback")
                        self._activate_fallback_for_session(session)
                
                time.sleep(self.fallback_check_interval)
                
            except Exception as e:
                logger.error(f"Error in hook activity monitor: {e}")
                time.sleep(10)
    
    def _fallback_monitor(self):
        """Fallback polling monitor (simplified from multi_monitor)"""
        while self.running:
            try:
                if not self.fallback_active:
                    time.sleep(5)
                    continue
                
                # Get active sessions
                active_sessions = set(session_manager.get_all_claude_sessions())
                
                for session_name in active_sessions:
                    if not self._should_monitor_session(session_name):
                        continue
                    
                    # Check session state
                    current_state = self.state_analyzer.get_state(session_name)
                    previous_state = self.last_state.get(session_name, SessionState.UNKNOWN)
                    
                    # Update state tracking
                    self.last_state[session_name] = current_state
                    
                    # Check for completion notification
                    if self._should_send_fallback_notification(session_name, previous_state, current_state):
                        self._send_fallback_notification(session_name)
                        self.metrics["fallback_triggers"] += 1
                
                time.sleep(self.config.check_interval)
                
            except Exception as e:
                logger.error(f"Error in fallback monitor: {e}")
                time.sleep(10)
    
    def _should_monitor_session(self, session_name: str) -> bool:
        """Determine if session should be monitored by fallback"""
        if not self.fallback_active:
            return False
        
        # Don't monitor if hooks are working for this session
        if self.hook_mode_active and session_name in self.last_hook_activity:
            last_activity = self.last_hook_activity[session_name]
            if datetime.now() - last_activity < self.hook_timeout:
                return False
        
        return True
    
    def _should_send_fallback_notification(self, session_name: str, prev_state: SessionState, curr_state: SessionState) -> bool:
        """Check if fallback notification should be sent"""
        current_time = time.time()
        last_notification = self.last_notification_time.get(session_name, 0)
        
        # Cooldown check
        if current_time - last_notification < self.notification_cooldown:
            return False
        
        # State transition check (simplified)
        should_notify = (
            (prev_state == SessionState.WORKING and curr_state != SessionState.WORKING) or
            (curr_state == SessionState.WAITING_INPUT and prev_state != SessionState.WAITING_INPUT)
        )
        
        if should_notify:
            self.last_notification_time[session_name] = current_time
        
        return should_notify
    
    def _send_fallback_notification(self, session_name: str):
        """Send notification via fallback system"""
        try:
            # Temporarily switch to target session
            original_session = session_manager.get_active_session()
            session_manager.switch_session(session_name)
            
            # Send notification
            success = self.notifier.send_work_completion_notification()
            
            # Switch back
            session_manager.switch_session(original_session)
            
            if success:
                logger.info(f"📤 Fallback notification sent for {session_name}")
                self.metrics["notifications_sent"] += 1
            else:
                logger.debug(f"🔇 Fallback notification skipped for {session_name}")
                
        except Exception as e:
            logger.error(f"Error sending fallback notification for {session_name}: {e}")
    
    def _activate_fallback_for_session(self, session_name: str):
        """Activate fallback monitoring for specific session"""
        self.fallback_active = True
        if session_name in self.last_hook_activity:
            del self.last_hook_activity[session_name]
        logger.info(f"🔄 Fallback activated for session: {session_name}")
    
    def _health_check(self):
        """Perform system health checks"""
        try:
            # Check hook system health
            if self.hook_mode_active:
                hook_status = self.hook_manager.get_hook_status()
                if not hook_status.get("script_executable", False):
                    logger.warning("Hook script not executable, switching to fallback")
                    self.hook_mode_active = False
                    self.fallback_active = True
            
            # Log current status every 5 minutes
            if hasattr(self, '_last_health_log'):
                if time.time() - self._last_health_log > 300:  # 5 minutes
                    self._log_system_status()
            else:
                self._last_health_log = time.time()
                
        except Exception as e:
            logger.error(f"Health check error: {e}")
    
    def _log_system_status(self):
        """Log current system status"""
        active_sessions = len(session_manager.get_all_claude_sessions())
        uptime = datetime.now() - self.metrics["start_time"]
        
        logger.info(f"📊 Hybrid Monitor Status: "
                   f"Sessions={active_sessions}, "
                   f"Hooks={'✅' if self.hook_mode_active else '❌'}, "
                   f"Fallback={'✅' if self.fallback_active else '❌'}, "
                   f"Uptime={str(uptime).split('.')[0]}")
        
        self._last_health_log = time.time()
    
    def _update_metrics(self):
        """Update performance metrics"""
        while self.running:
            try:
                # Update metrics periodically
                time.sleep(60)  # Update every minute
                
                # Log metrics every hour
                if hasattr(self, '_last_metrics_log'):
                    if time.time() - self._last_metrics_log > 3600:  # 1 hour
                        self._log_metrics()
                else:
                    self._last_metrics_log = time.time()
                    
            except Exception as e:
                logger.error(f"Metrics update error: {e}")
                time.sleep(60)
    
    def _log_metrics(self):
        """Log performance metrics"""
        uptime_hours = (datetime.now() - self.metrics["start_time"]).total_seconds() / 3600
        
        logger.info(f"📈 Performance Metrics (last {uptime_hours:.1f}h): "
                   f"Hook triggers: {self.metrics['hook_triggers']}, "
                   f"Fallback triggers: {self.metrics['fallback_triggers']}, "
                   f"Notifications sent: {self.metrics['notifications_sent']}, "
                   f"Hook failures: {self.metrics['hook_failures']}")
        
        self._last_metrics_log = time.time()
    
    def record_hook_activity(self, session_name: str):
        """Record hook activity for a session"""
        self.last_hook_activity[session_name] = datetime.now()
        self.metrics["hook_triggers"] += 1
        logger.debug(f"🎣 Hook activity recorded for {session_name}")
    
    def stop_monitoring(self):
        """Stop hybrid monitoring system"""
        logger.info("🛑 Stopping hybrid monitoring...")
        self.running = False
    
    def get_status(self) -> Dict:
        """Get current hybrid monitor status"""
        uptime = datetime.now() - self.metrics["start_time"]
        active_sessions = session_manager.get_all_claude_sessions()
        
        return {
            "mode": "hybrid",
            "running": self.running,
            "hook_mode_active": self.hook_mode_active,
            "fallback_active": self.fallback_active,
            "active_sessions": len(active_sessions),
            "session_list": active_sessions,
            "uptime_seconds": uptime.total_seconds(),
            "metrics": self.metrics.copy(),
            "hook_status": self.hook_manager.get_hook_status()
        }


def main():
    """Main entry point for hybrid monitoring"""
    try:
        config = ClaudeOpsConfig()
        monitor = HybridMonitor(config)
        
        logger.info("🚀 Starting Hybrid Monitor...")
        monitor.start_monitoring()
        
    except KeyboardInterrupt:
        logger.info("Hybrid monitor stopped by user")
    except Exception as e:
        logger.error(f"Hybrid monitor error: {e}")
        raise


if __name__ == "__main__":
    main()