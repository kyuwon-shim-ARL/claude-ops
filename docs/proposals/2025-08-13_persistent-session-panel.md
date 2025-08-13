# PRD: Claude-Ops 상시 세션 패널 (Persistent Session Panel)

**작성일:** 2025-08-13  
**작성자:** Claude & Kyuwon  
**상태:** Planning  
**프로젝트:** Claude-Ops Telegram Bot UX Enhancement

---

## 📝 Executive Summary

### 1. **문제 정의**

**현재 문제:**
- 긴 알림 메시지로 인해 이전 세션에 답장하려면 많은 스크롤 필요
- `/sessions` 명령어를 매번 호출해야 세션 목록 확인 가능
- 직전 세션이 아닌 경우 대화 히스토리에서 찾기 어려움
- 세션 전환 시 UI 조작이 번거로움
- **알림 수신 시 마지막 프롬프트 기억 안 남**: 작업 컨텍스트 파악 어려움
- **현재 활성 세션 구분 어려움**: 어느 세션이 활성화되어 있는지 불분명
- **로그 조회 시 고정된 50줄**: 상황에 따른 유연한 로그 길이 조절 불가

**사용자 시나리오:**
```
1. 여러 세션에서 알림 수신
2. PaperFlow 세션에 답장하고 싶음
3. 현재: 스크롤 올리기 → 해당 메시지 찾기 → 답장
4. 개선 후: 상시 패널에서 PaperFlow 클릭 → 바로 상호작용
```

### 2. **목표**

**Primary Goal:**
- 상시 세션 패널을 통한 원클릭 세션 접근

**Success Criteria:**
- [ ] 최근 사용 세션 3-6개 항상 표시
- [ ] 원클릭으로 세션 상호작용 메뉴 접근
- [ ] 스크롤 없이 모든 세션 관리 가능
- [ ] Freqtrade 스타일의 직관적 UI
- [ ] **알림 메시지에 마지막 프롬프트 표시로 컨텍스트 회상 지원**
- [ ] **현재 활성 세션 시각적 강조 표시**
- [ ] **로그 길이 동적 조절 (100/150/200/300줄) 버튼 제공**

---

## 🎯 솔루션 설계

### 1. **상시 패널 구조**

#### A. Pinned Message with Inline Keyboard
```
📊 Claude-Ops 세션 패널 (Auto-updated)

🎯 claude_PaperFlow      [●] WORKING  ⭐ (현재 활성)
🔬 claude_claude-dev-kit [○] IDLE  
🤖 claude_claude-ops     [●] WORKING
🧪 claude_MC             [○] IDLE
💊 claude_SMILES         [△] WAITING

[새로고침] [설정] [도움말]
```

**개선사항:**
- **⭐ 현재 활성 세션 표시**: 활성 세션을 ⭐ 아이콘으로 강조
- **모든 세션 표시**: 최근 사용 기준으로 정렬하되 모든 세션 포함
- **스마트 정렬**: 활성 세션 → WORKING → WAITING → ERROR → IDLE 순서

#### B. Dynamic Button Layout
```python
# 세션 상태별 이모지 매핑
STATUS_EMOJI = {
    SessionState.WORKING: "●",        # 작업 중
    SessionState.WAITING_INPUT: "△",  # 입력 대기
    SessionState.IDLE: "○",           # 유휴
    SessionState.ERROR: "❌",         # 오류
    SessionState.UNKNOWN: "❓"        # 알 수 없음
}

# 세션 타입별 이모지 (프로젝트 구분)
SESSION_TYPE_EMOJI = {
    "PaperFlow": "🎯",
    "claude-dev-kit": "🔬", 
    "claude-ops": "🤖",
    "MC": "🧪",
    "SMILES": "💊"
}
```

### 2. **세션 선택 후 액션 패널**

세션 버튼 클릭 시 나타나는 상호작용 메뉴:

```
🎯 claude_PaperFlow 관리

현재 상태: [●] WORKING
마지막 활동: 2분 전

[📋 로그 보기] [⏸️ 일시정지] [🗑️ 화면 지우기]
[🔄 세션 전환] [📊 상태 새로고침] [🔙 패널로 돌아가기]
```

#### 로그 보기 개선 - 동적 길이 조절
로그 보기 버튼 클릭 시:

```
📋 claude_PaperFlow 로그 (최근 50줄)

[로그 내용 표시...]

📏 로그 길이 조절:
[100줄] [150줄] [200줄] [300줄] [🔙 뒤로]
```

**로그 길이 조절 기능:**
- **기본값**: 50줄 (현재 유지)
- **동적 조절**: 100/150/200/300줄 버튼으로 즉시 변경
- **상태 유지**: 사용자별 선호 길이 기억
- **스마트 로딩**: 긴 로그는 페이지네이션으로 성능 최적화

### 3. **마지막 프롬프트 회상 시스템** ⭐ NEW

알림 메시지에 사용자의 마지막 프롬프트를 표시하여 컨텍스트 회상 지원:

#### A. 알림 메시지 구조 개선
```
🎯 claude_PaperFlow 작업 완료!

📤 마지막 요청: "데이터 분석 결과를 그래프로 시각화해서 보여줘. 특히 correlation matrix와..."
   ...(중간 생략)..."...성능 지표도 같이 포함해서 정리해줘"

📊 작업 결과:
[현재 작업 결과 내용...]

💡 빠른 응답: 이 결과에 대해 추가로 질문하시거나 다음 작업을 요청하세요.
```

#### B. 프롬프트 스마트 트렁케이션
```python
class PromptRecallSystem:
    """마지막 프롬프트 회상 시스템"""
    
    def extract_last_user_prompt(self, session_name: str) -> str:
        """마지막 사용자 프롬프트 추출"""
        # tmux 히스토리에서 마지막 사용자 입력 찾기
        # 일반적으로 "> " 이후의 텍스트
        pass
    
    def smart_truncate_prompt(self, prompt: str, max_length: int = 200) -> str:
        """프롬프트 지능형 자르기"""
        if len(prompt) <= max_length:
            return f'"{prompt}"'
            
        # 전략 1: 앞 + 뒤 보존 (중간 생략)
        if len(prompt) > max_length:
            front_keep = max_length // 2 - 20
            back_keep = max_length // 2 - 20
            
            front_part = prompt[:front_keep]
            back_part = prompt[-back_keep:]
            
            return f'"{front_part}...(중간 생략)...{back_part}"'
```

#### C. 프롬프트 감지 패턴
```python
# Claude Code 환경의 사용자 입력 패턴 감지
USER_INPUT_PATTERNS = [
    r'> (.+)',           # 일반적인 프롬프트
    r'Human: (.+)',      # Claude Code 대화 패턴
    r'user: (.+)',       # 터미널 사용자 입력
    r'Question: (.+)',   # 질문 패턴
]

def detect_user_prompts(screen_content: str) -> List[str]:
    """화면에서 사용자 프롬프트들 추출"""
    prompts = []
    for line in screen_content.split('\n'):
        for pattern in USER_INPUT_PATTERNS:
            match = re.search(pattern, line)
            if match:
                prompts.append(match.group(1).strip())
    return prompts
```

### 4. **자동 업데이트 메커니즘**

#### A. 실시간 상태 업데이트
```python
class PersistentPanel:
    def __init__(self):
        self.panel_message_id = None
        self.last_update = datetime.now()
        self.update_interval = 30  # 30초마다 업데이트
        
    async def auto_update_panel(self):
        """패널 자동 업데이트"""
        current_sessions = self.get_recent_sessions()
        new_content = self.generate_panel_content(current_sessions)
        
        if self.content_changed(new_content):
            await self.update_pinned_message(new_content)
```

#### B. 이벤트 기반 즉시 업데이트
```python
# 상태 변경 시 즉시 패널 업데이트
def on_session_state_change(session_name, old_state, new_state):
    if self.panel_contains_session(session_name):
        asyncio.create_task(self.update_panel_immediately())
```

---

## 🔧 기술 구현 계획

### Phase 1: 기본 패널 + 프롬프트 회상 (Week 1)

#### 1.1 Persistent Panel Manager (Enhanced)
```python
class PersistentSessionPanel:
    """상시 세션 패널 관리자"""
    
    def __init__(self, bot, chat_id):
        self.bot = bot
        self.chat_id = chat_id
        self.panel_message_id = None
        self.recent_sessions = []
        
    async def initialize_panel(self):
        """패널 초기화 및 고정"""
        content = self.generate_panel_content()
        message = await self.bot.send_message(
            self.chat_id, 
            content, 
            reply_markup=self.get_panel_keyboard()
        )
        self.panel_message_id = message.message_id
        await self.bot.pin_chat_message(self.chat_id, message.message_id)
        
    def generate_panel_content(self) -> str:
        """패널 콘텐츠 생성 (활성 세션 강조 포함)"""
        lines = ["📊 Claude-Ops 세션 패널 (Auto-updated)\n"]
        
        # 스마트 정렬: 활성 → WORKING → WAITING → ERROR → IDLE
        sessions = self.get_smart_sorted_sessions()
        active_session = self.get_active_session()
        
        for session in sessions:
            status = self.get_session_status(session)
            emoji = SESSION_TYPE_EMOJI.get(session.type, "🔧")
            status_emoji = STATUS_EMOJI.get(status.state, "❓")
            
            # 활성 세션 강조
            active_indicator = " ⭐ (현재 활성)" if session.name == active_session else ""
            
            lines.append(f"{emoji} {session.name} [{status_emoji}] {status.state.value.upper()}{active_indicator}")
            
        lines.append(f"\n⏰ 마지막 업데이트: {datetime.now().strftime('%H:%M:%S')}")
        return "\n".join(lines)
    
    def get_smart_sorted_sessions(self) -> List[Session]:
        """스마트 정렬된 세션 목록 반환"""
        all_sessions = session_manager.get_all_claude_sessions()
        active_session = self.get_active_session()
        
        def sort_key(session):
            # 정렬 우선순위: 활성(0) → WORKING(1) → WAITING(2) → ERROR(3) → IDLE(4)
            if session.name == active_session:
                return 0
            state = self.get_session_status(session).state
            priority = {
                SessionState.WORKING: 1,
                SessionState.WAITING_INPUT: 2,
                SessionState.ERROR: 3,
                SessionState.IDLE: 4,
                SessionState.UNKNOWN: 5
            }
            return priority.get(state, 6)
        
        return sorted(all_sessions, key=sort_key)
    
    def get_panel_keyboard(self) -> InlineKeyboardMarkup:
        """패널 키보드 생성"""
        keyboard = []
        
        # 세션 버튼들 (최대 6개, 2열 배치)
        session_buttons = []
        for i, session in enumerate(self.get_recent_sessions()):
            button_text = f"{session.display_name}"
            callback_data = f"session:{session.name}"
            session_buttons.append(InlineKeyboardButton(button_text, callback_data=callback_data))
            
            # 2개씩 한 줄에 배치
            if len(session_buttons) == 2 or i == len(self.recent_sessions) - 1:
                keyboard.append(session_buttons)
                session_buttons = []
        
        # 하단 메뉴 버튼들
        keyboard.append([
            InlineKeyboardButton("🔄 새로고침", callback_data="panel:refresh"),
            InlineKeyboardButton("⚙️ 설정", callback_data="panel:settings"),
            InlineKeyboardButton("❓ 도움말", callback_data="panel:help")
        ])
        
        return InlineKeyboardMarkup(keyboard)
```

#### 1.2 Enhanced Notification with Prompt Recall
```python
class EnhancedNotifier(SmartNotifier):
    """프롬프트 회상 기능이 포함된 개선된 알림"""
    
    def __init__(self, config):
        super().__init__(config)
        self.prompt_recall = PromptRecallSystem()
    
    def send_work_completion_notification_with_context(self) -> bool:
        """컨텍스트가 포함된 작업 완료 알림"""
        session_name = self.config.session_name
        
        # 기존 작업 결과 추출
        work_context = self.extract_work_context()
        
        # 마지막 프롬프트 추출 및 표시
        last_prompt = self.prompt_recall.extract_last_user_prompt(session_name)
        truncated_prompt = self.prompt_recall.smart_truncate_prompt(last_prompt, 200)
        
        # 개선된 알림 메시지 구성
        enhanced_message = f"""
🎯 {session_name} 작업 완료!

📤 마지막 요청: {truncated_prompt}

📊 작업 결과:
{work_context}

💡 빠른 응답: 이 결과에 대해 추가로 질문하시거나 다음 작업을 요청하세요.
"""
        
        return self.send_notification_sync(enhanced_message)

class PromptRecallSystem:
    """마지막 프롬프트 회상 시스템"""
    
    def extract_last_user_prompt(self, session_name: str) -> str:
        """마지막 사용자 프롬프트 추출"""
        try:
            # tmux 히스토리에서 사용자 입력 패턴 찾기
            result = subprocess.run(
                f"tmux capture-pane -t {session_name} -p -S -2000",  # 더 긴 히스토리 검색
                shell=True, capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                prompts = self.detect_user_prompts(result.stdout)
                return prompts[-1] if prompts else "프롬프트를 찾을 수 없습니다"
            
        except Exception as e:
            logger.warning(f"Failed to extract user prompt: {e}")
            
        return "프롬프트 추출 실패"
    
    def detect_user_prompts(self, screen_content: str) -> List[str]:
        """화면에서 사용자 프롬프트들 추출"""
        import re
        prompts = []
        
        # Claude Code 환경의 사용자 입력 패턴
        patterns = [
            r'Human: (.+?)(?=\n\n|\nAssistant:|$)',          # Claude Code 대화
            r'> (.+?)(?=\n|$)',                              # 일반 프롬프트  
            r'user: (.+?)(?=\n|$)',                          # 터미널 입력
            r'You: (.+?)(?=\n|$)',                           # 대화 형태
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, screen_content, re.MULTILINE | re.DOTALL)
            for match in matches:
                clean_prompt = match.strip()
                if len(clean_prompt) > 10:  # 최소 길이 필터
                    prompts.append(clean_prompt)
        
        return prompts
    
    def smart_truncate_prompt(self, prompt: str, max_length: int = 200) -> str:
        """프롬프트 지능형 자르기"""
        if len(prompt) <= max_length:
            return f'"{prompt}"'
        
        # 앞뒤 보존 전략
        front_keep = max_length // 2 - 15
        back_keep = max_length // 2 - 15
        
        front_part = prompt[:front_keep].strip()
        back_part = prompt[-back_keep:].strip()
        
        return f'"{front_part}...(중간 생략)...{back_part}"'
```

#### 1.3 Session Action Handler with Dynamic Log
```python
class SessionActionHandler:
    """세션별 액션 처리"""
    
    async def handle_session_select(self, session_name: str):
        """세션 선택 시 액션 메뉴 표시"""
        session_info = self.get_session_info(session_name)
        
        content = f"""
🎯 {session_name} 관리

현재 상태: [{STATUS_EMOJI[session_info.state]}] {session_info.state.value.upper()}
마지막 활동: {session_info.last_activity_ago}
화면 크기: {len(session_info.screen_content)} 문자

📍 빠른 액션을 선택하세요:
"""
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📋 로그 보기", callback_data=f"action:{session_name}:log"),
                InlineKeyboardButton("⏸️ 일시정지", callback_data=f"action:{session_name}:pause")
            ],
            [
                InlineKeyboardButton("🗑️ 화면 지우기", callback_data=f"action:{session_name}:clear"),
                InlineKeyboardButton("🔄 세션 전환", callback_data=f"action:{session_name}:switch")
            ],
            [
                InlineKeyboardButton("📊 상태 새로고침", callback_data=f"action:{session_name}:refresh"),
                InlineKeyboardButton("🔙 패널로 돌아가기", callback_data="panel:return")
            ]
        ])
        
        await self.bot.edit_message_text(
            content,
            chat_id=self.chat_id,
            message_id=self.panel_message_id,
            reply_markup=keyboard
        )
    
    async def handle_log_view(self, session_name: str, lines: int = 50):
        """동적 길이 조절이 가능한 로그 보기"""
        try:
            # tmux에서 지정된 줄 수만큼 로그 가져오기
            result = subprocess.run(
                f"tmux capture-pane -t {session_name} -p -S -{lines}",
                shell=True, capture_output=True, text=True, timeout=10
            )
            
            if result.returncode == 0:
                log_content = result.stdout.strip()
                
                # 길이 제한 적용 (Telegram 4096자 제한)
                if len(log_content) > 3000:
                    log_content = log_content[-3000:] + "\n...(로그가 길어서 일부만 표시)"
                
                content = f"""
📋 {session_name} 로그 (최근 {lines}줄)

```
{log_content}
```

📏 로그 길이 조절:
"""
                
                # 동적 길이 조절 버튼
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("100줄", callback_data=f"log:{session_name}:100"),
                        InlineKeyboardButton("150줄", callback_data=f"log:{session_name}:150"),
                        InlineKeyboardButton("200줄", callback_data=f"log:{session_name}:200"),
                        InlineKeyboardButton("300줄", callback_data=f"log:{session_name}:300")
                    ],
                    [
                        InlineKeyboardButton("🔄 새로고침", callback_data=f"log:{session_name}:{lines}"),
                        InlineKeyboardButton("🔙 세션 메뉴로", callback_data=f"session:{session_name}")
                    ]
                ])
                
                await self.bot.edit_message_text(
                    content,
                    chat_id=self.chat_id,
                    message_id=self.panel_message_id,
                    reply_markup=keyboard
                )
                
            else:
                await self.show_error_message(f"로그를 가져올 수 없습니다: {result.stderr}")
                
        except Exception as e:
            await self.show_error_message(f"로그 조회 중 오류: {str(e)}")
    
    def get_user_preferred_log_length(self, user_id: str) -> int:
        """사용자별 선호 로그 길이 반환"""
        # 사용자 설정 저장소에서 조회 (기본값: 50)
        return self.user_preferences.get(user_id, {}).get('log_length', 50)
    
    def save_user_preferred_log_length(self, user_id: str, length: int):
        """사용자별 선호 로그 길이 저장"""
        if user_id not in self.user_preferences:
            self.user_preferences[user_id] = {}
        self.user_preferences[user_id]['log_length'] = length
        # 영구 저장 (파일이나 DB)
        self.save_user_preferences()
```

### Phase 2: 고급 기능 (Week 2)

#### 2.1 Recent Sessions 관리
```python
class RecentSessionsManager:
    """최근 세션 추적 및 관리"""
    
    def __init__(self, max_sessions=6):
        self.max_sessions = max_sessions
        self.session_activity = {}  # session_name -> last_activity_time
        self.session_interactions = {}  # session_name -> interaction_count
        
    def update_session_activity(self, session_name: str):
        """세션 활동 업데이트"""
        now = datetime.now()
        self.session_activity[session_name] = now
        self.session_interactions[session_name] = self.session_interactions.get(session_name, 0) + 1
        
    def get_recent_sessions(self) -> List[str]:
        """최근 활동 기준 상위 세션들 반환"""
        # 활동 시간과 상호작용 횟수를 조합한 점수 계산
        scored_sessions = []
        now = datetime.now()
        
        for session_name in session_manager.get_all_claude_sessions():
            last_activity = self.session_activity.get(session_name, now - timedelta(days=30))
            interaction_count = self.session_interactions.get(session_name, 0)
            
            # 점수 = 최근성 점수 + 상호작용 점수
            recency_score = max(0, 100 - (now - last_activity).total_seconds() / 3600)  # 시간당 1점 차감
            interaction_score = min(50, interaction_count * 5)  # 상호작용당 5점, 최대 50점
            
            total_score = recency_score + interaction_score
            scored_sessions.append((session_name, total_score))
            
        # 점수 순으로 정렬하여 상위 N개 반환
        scored_sessions.sort(key=lambda x: x[1], reverse=True)
        return [session for session, _ in scored_sessions[:self.max_sessions]]
```

#### 2.2 Smart Panel Updates
```python
class SmartPanelUpdater:
    """지능형 패널 업데이트"""
    
    def should_update_panel(self, changes: dict) -> bool:
        """패널 업데이트 필요성 판단"""
        significant_changes = [
            'state_change',      # 상태 변경
            'new_session',       # 새 세션 추가  
            'session_removed',   # 세션 제거
            'error_occurred'     # 오류 발생
        ]
        
        return any(change in significant_changes for change in changes.keys())
    
    async def batch_update_panel(self):
        """배치 업데이트 (30초마다)"""
        if self.pending_changes and self.should_update_panel(self.pending_changes):
            await self.update_panel()
            self.pending_changes.clear()
```

### Phase 3: 사용자 경험 최적화 (Week 3)

#### 3.1 Context-Aware Actions
```python
class ContextAwareActions:
    """컨텍스트 인식 액션"""
    
    def get_contextual_actions(self, session_name: str) -> List[dict]:
        """세션 상태에 따른 맞춤 액션 제공"""
        session_state = self.state_analyzer.get_state(session_name)
        actions = []
        
        if session_state == SessionState.WORKING:
            actions.extend([
                {"text": "⏸️ 작업 중단", "action": "interrupt"},
                {"text": "📊 진행 상황", "action": "progress"}
            ])
        elif session_state == SessionState.WAITING_INPUT:
            actions.extend([
                {"text": "✅ 예", "action": "answer_yes"},
                {"text": "❌ 아니오", "action": "answer_no"},
                {"text": "📋 선택지 보기", "action": "show_options"}
            ])
        elif session_state == SessionState.ERROR:
            actions.extend([
                {"text": "🔧 오류 보기", "action": "show_error"},
                {"text": "🔄 재시작", "action": "restart"}
            ])
            
        # 공통 액션
        actions.extend([
            {"text": "📋 로그 보기", "action": "log"},
            {"text": "🔄 세션 전환", "action": "switch"}
        ])
        
        return actions
```

#### 3.2 Quick Actions
```python
# 빠른 액션 처리
async def handle_quick_action(self, session_name: str, action: str):
    """빠른 액션 처리"""
    if action == "answer_yes":
        await self.send_to_session(session_name, "1")  # 일반적으로 1번이 Yes
    elif action == "answer_no":
        await self.send_to_session(session_name, "2")  # 일반적으로 2번이 No
    elif action == "interrupt":
        await self.send_interrupt_signal(session_name)
    elif action == "show_options":
        screen_content = self.get_screen_content(session_name)
        options = self.extract_options(screen_content)
        await self.show_options_dialog(options)
```

---

## 📊 사용자 시나리오

### 시나리오 1: 일반적인 사용
```
1. 사용자가 Telegram을 열면 상단에 고정된 세션 패널 확인
2. "🎯 claude_PaperFlow [△] WAITING" 버튼 클릭
3. 세션 관리 메뉴에서 "📋 로그 보기" 선택
4. 로그 확인 후 적절한 답변 입력
5. 패널로 돌아가서 다른 세션 확인
```

### 시나리오 2: 빠른 응답
```
1. WAITING 상태인 세션 클릭
2. 컨텍스트 인식으로 "✅ 예" / "❌ 아니오" 버튼 제공
3. 원클릭으로 즉시 응답 완료
4. 패널이 자동으로 상태 업데이트 (WAITING → WORKING)
```

### 시나리오 3: 오류 처리
```
1. 패널에서 "🤖 claude-ops [❌] ERROR" 확인
2. 세션 클릭 → "🔧 오류 보기" 선택
3. 오류 내용 확인 후 "🔄 재시작" 클릭
4. 자동으로 세션 재시작 및 상태 정상화
```

---

## 🛠 구현 우선순위

### High Priority
- [ ] 기본 상시 패널 구현
- [ ] 세션 선택 및 액션 메뉴
- [ ] 자동 상태 업데이트
- [ ] 최근 세션 추적

### Medium Priority  
- [ ] 컨텍스트 인식 액션
- [ ] 빠른 응답 버튼
- [ ] 패널 설정 메뉴
- [ ] 사용자 맞춤 설정

### Low Priority
- [ ] 패널 테마 변경
- [ ] 통계 및 분석 기능
- [ ] 고급 필터링
- [ ] 알림 설정 통합

---

## 📈 성공 지표

### Quantitative Metrics
- **접근 시간 단축**: 세션 접근 시간 80% 감소 (10초 → 2초)
- **스크롤 횟수**: 평균 스크롤 90% 감소
- **클릭 수**: 세션 관리 클릭 50% 감소
- **사용 빈도**: 패널 사용률 90%+
- **컨텍스트 회상**: 프롬프트 회상으로 재질문 80% 감소
- **로그 조회 효율**: 동적 길이 조절로 로그 조회 시간 60% 단축

### Qualitative Metrics
- **사용성**: 직관적이고 빠른 세션 전환
- **효율성**: 원클릭 액세스로 워크플로우 개선
- **만족도**: Freqtrade 수준의 UX 제공
- **안정성**: 패널 업데이트 안정성 99%+
- **컨텍스트 인식**: 마지막 프롬프트 표시로 작업 연속성 확보
- **개인화**: 사용자별 선호 설정 (로그 길이 등) 지원

---

## 🎯 Next Steps

1. **Immediate** (Today):
   - [x] PRD 작성 및 검토 (프롬프트 회상, 활성 세션 강조, 동적 로그 포함)
   - [ ] 프롬프트 추출 패턴 연구 (Claude Code, tmux 환경)
   - [ ] Telegram Bot API 인라인 키보드 및 메시지 편집 연구

2. **Short-term** (This Week):
   - [ ] PersistentSessionPanel 클래스 구현 (활성 세션 강조 포함)
   - [ ] PromptRecallSystem 구현 및 테스트
   - [ ] EnhancedNotifier 구현 (컨텍스트 포함 알림)
   - [ ] Dynamic Log Viewer 구현 (100/150/200/300줄 버튼)
   - [ ] 사용자 설정 저장소 구현

3. **Long-term** (Next Week):
   - [ ] 모든 세션 표시 및 스마트 정렬 구현
   - [ ] 사용자별 개인화 설정 (로그 길이 선호도 등)
   - [ ] 통합 테스트 및 성능 최적화
   - [ ] 프로덕션 배포 및 모니터링

---

## 📚 References

- [Telegram Bot API - Inline Keyboards](https://core.telegram.org/bots/api#inlinekeyboard)
- [Freqtrade Telegram Bot UI](https://www.freqtrade.io/en/stable/telegram-usage/)
- [Pinned Messages Best Practices](https://core.telegram.org/bots/api#pinchatmessage)
- Current Claude-Ops Telegram Bot Implementation

---

## 🌟 새로 추가된 핵심 기능 요약

### 1. **📤 마지막 프롬프트 회상 시스템**
```
🎯 claude_PaperFlow 작업 완료!

📤 마지막 요청: "데이터 분석 결과를 그래프로 시각화해서..."
   ...(중간 생략)..."...성능 지표도 같이 포함해서 정리해줘"

📊 작업 결과: [결과 내용]
💡 빠른 응답: 이 결과에 대해 추가로 질문하시거나...
```

### 2. **⭐ 현재 활성 세션 강조 표시**
```
🎯 claude_PaperFlow      [●] WORKING  ⭐ (현재 활성)
🔬 claude_claude-dev-kit [○] IDLE  
🤖 claude_claude-ops     [●] WORKING
```

### 3. **📏 동적 로그 길이 조절**
```
📋 claude_PaperFlow 로그 (최근 50줄)
[로그 내용...]

📏 로그 길이 조절:
[100줄] [150줄] [200줄] [300줄] [🔙 뒤로]
```

### 🎯 **종합 사용자 경험 개선**

**Before (현재):**
1. 알림 수신 → 스크롤 올리기 → 이전 대화 찾기 → 무엇을 요청했는지 기억 안 남 → 다시 로그 확인 → 50줄로는 부족해서 명령어 다시 입력

**After (개선 후):**
1. 알림 수신 → 마지막 프롬프트까지 포함된 완전한 컨텍스트 확인 → 상시 패널에서 해당 세션 클릭 → 필요시 원클릭으로 로그 길이 조절 → 즉시 후속 작업 진행

**핵심 가치:**
- 🧠 **기억 부담 제거**: 마지막 프롬프트 자동 표시
- 👁️ **시각적 직관성**: 현재 활성 세션 명확한 구분
- ⚡ **즉시 대응**: 스크롤 없이 바로 필요한 정보 접근
- 🎛️ **유연한 제어**: 상황에 맞는 로그 길이 선택

---

*이 문서는 Claude-Ops Telegram Bot의 사용자 경험을 혁신적으로 개선하기 위한 상시 세션 패널 기능의 제품 요구사항 문서입니다. 추가된 프롬프트 회상, 활성 세션 강조, 동적 로그 조절 기능으로 완전한 UX 혁신을 달성합니다.*