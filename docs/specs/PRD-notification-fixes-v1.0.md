# PRD: Claude-Ops Notification System Fixes v1.0

## 📋 Executive Summary
Fix critical notification timing issues and simplify the system by removing unnecessary complexity.

## 🎯 Objectives
1. Fix false completion notifications when "esc to interrupt" is present
2. Remove unnecessary notification priorities (CRITICAL, INFO)
3. Remove non-functional bot commands
4. Fix session summary "추정" display logic

## 📊 Current Problems

### P0: False Completion Notifications
- **Issue**: Completion notifications sent while Claude is still working
- **Root Cause**: Prompt '>' has higher priority than "esc to interrupt" pattern
- **Impact**: User confusion, reduced trust in notification system

### P1: Session Summary Inaccuracy
- **Issue**: Shows "추정" even when actual notification times exist
- **Root Cause**: Incorrect has_record logic
- **Impact**: Misleading information in summary displays

### P2: System Complexity
- **Issue**: Unnecessary notification priorities and unused commands
- **Root Cause**: Feature creep without cleanup
- **Impact**: Code maintenance burden, potential bugs

## 🔧 Proposed Solutions

### 1. State Detection Priority Fix

#### Current (Broken):
```python
# Prompt check has priority over working patterns
1. Check for prompts → if found, return IDLE
2. Check for "esc to interrupt" → too late
```

#### Proposed (Fixed):
```python
# Working patterns have absolute priority
1. Check for "esc to interrupt" → if found, return WORKING
2. Only then check for prompts
```

### 2. Notification System Simplification

#### Remove Notification Priorities:
- ❌ CRITICAL_ALERT - Remove completely
- ❌ HIGH_PRIORITY - Remove completely
- ❌ INFO - Remove completely
- ✅ Keep only: Work completion and Input waiting notifications

#### Simplified Notification Logic:
```python
class NotificationType(Enum):
    WORK_COMPLETE = "work_complete"
    WAITING_INPUT = "waiting_input"
    # That's it. No priorities, no levels.
```

### 3. Bot Command Cleanup

#### Commands to Remove:
- ❌ `/detect_status` - Non-functional
- ❌ `/detect_trend` - Non-functional
- ❌ `/fix_terminal` - Non-functional

#### Remaining Commands:
- ✅ `/sessions` - Session management
- ✅ `/new-project` - Project creation
- ✅ `/board` - Session board view
- ✅ `/restart` - Session restart
- ✅ `/stop` - Stop work
- ✅ `/erase` - Clear input
- ✅ `/status` - Bot status
- ✅ `/log` - View logs
- ✅ `/fullcycle` - Workflow execution
- ✅ `/help` - Help

### 4. Session Summary Fix

#### Current (Broken):
```python
# Complex logic with fallback estimates
if not has_record:  # Incorrect condition
    message += f"({wait_str} 대기 ~추정~)"
```

#### Proposed (Fixed):
```python
# Simple: if we have notification time, show it
if last_notification_time:
    message += f"({wait_str} 대기)"
else:
    message += f"({wait_str} 대기 ~추정~)"
```

## 📐 Technical Specifications

### File Changes Required:

#### 1. `claude_ops/utils/session_state.py`
- Line 313-365: Reorder detection priority
- Add "esc to interrupt" as absolute first check
- Move prompt detection after working pattern detection

#### 2. `claude_ops/utils/conservative_detector.py`
- Strengthen "esc to interrupt" detection
- Add context awareness for TODO lists

#### 3. `claude_ops/telegram/notifier.py`
- Remove all priority-related code
- Simplify to 2 notification types only
- Remove TaskCompletion complexity

#### 4. `claude_ops/telegram/bot.py`
- Remove detect_status, detect_trend, fix_terminal handlers
- Clean up command list in help menu
- Update command registration

#### 5. `claude_ops/utils/session_summary.py`
- Lines 493-497: Fix "추정" display logic
- Simplify has_record checking
- Use actual notification times when available

## ✅ Success Criteria

### Functional Requirements:
1. No false completion notifications when "esc to interrupt" is visible
2. Session summary shows actual times (no "추정") when notifications were sent
3. Removed commands return "command not found" error
4. Only 2 notification types remain in system

### Non-Functional Requirements:
1. Code complexity reduced by 30%
2. All tests pass after changes
3. No regression in existing functionality

## 🧪 Test Plan

### Test Scenarios:

#### 1. State Detection Tests:
- Given: Screen shows "esc to interrupt" and prompt '>'
- When: State detection runs
- Then: Returns WORKING, not IDLE

#### 2. Notification Tests:
- Given: Claude is designing with todos active
- When: "esc to interrupt" is visible
- Then: No completion notification sent

#### 3. Summary Display Tests:
- Given: Session has sent notifications
- When: Summary is generated
- Then: Shows actual wait time without "추정"

#### 4. Command Removal Tests:
- Given: User types /detect_status
- When: Bot processes command
- Then: Returns "Unknown command" message

## 📅 Implementation Timeline

### Phase 1: Critical Fixes (Day 1)
- Fix state detection priority
- Fix session summary "추정" logic

### Phase 2: Simplification (Day 2)
- Remove notification priorities
- Clean up notification code

### Phase 3: Command Cleanup (Day 3)
- Remove unused bot commands
- Update help documentation

## 🎯 Expected Outcomes
1. **Accuracy**: 100% accurate work state detection
2. **Simplicity**: 50% less notification-related code
3. **Reliability**: Zero false positive notifications
4. **Clarity**: Accurate session summary information

## 📊 Risk Analysis

### Low Risk:
- Removing unused commands (no user impact)
- Simplifying notification types (improves clarity)

### Medium Risk:
- Changing state detection priority (needs thorough testing)
- Session summary logic changes (visible to users)

### Mitigation:
- Comprehensive test coverage before deployment
- Gradual rollout with monitoring
- Quick rollback plan if issues detected