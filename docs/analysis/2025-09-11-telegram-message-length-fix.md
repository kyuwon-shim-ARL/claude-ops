# 텔레그램 메시지 길이 제한 문제 분석 및 해결

## 📅 분석 정보
- **날짜**: 2025-09-11 14:30
- **요청**: sessions로 세션 전환 시 message too long 에러 해결
- **유형**: Bug Fix + UX Improvement

## 📊 분석 결과

### 문제 상황

#### 사용자 보고
- `/sessions` 명령어로 세션 전환 시 긴 로그가 있으면 에러 발생
- "Message too long" 에러로 전송 실패
- 기준이 너무 짧고, 에러보다는 자동 분할이 나음

#### 근본 원인
1. **`_switch_to_session()` 메서드의 메시지 길이 체크 누락**
   - `bot.py:1125` - 길이 체크 없이 직접 전송
   - 로그가 4096자 초과시 텔레그램 API 에러

2. **메시지 분할 유틸리티 미사용**
   - `split_long_message()` 함수 존재하지만 미사용
   - `safe_send_message()` 함수도 구현되어 있지만 미활용

3. **부적절한 제한값**
   - 실제 텔레그램 제한: 4096자
   - 설정값: 5000자 (실제 제한 초과)

### 해결 방안

#### 1. 자동 메시지 분할 적용
```python
# Before (문제 있던 코드)
await update.message.reply_text(full_message, parse_mode=None, reply_markup=reply_markup)

# After (수정된 코드)
if len(full_message) > get_telegram_max_length():
    await safe_send_message(
        update.message.reply_text,
        full_message,
        parse_mode=None,
        reply_markup=reply_markup,
        preserve_markdown=False
    )
else:
    await update.message.reply_text(full_message, parse_mode=None, reply_markup=reply_markup)
```

#### 2. 스마트 분할 기능
- 줄바꿈 경계에서 자연스럽게 분할
- 단어 중간 분할 방지
- 연속 메시지 표시 (_(계속)_)
- 마지막 메시지에만 버튼 추가

#### 3. 제한값 조정
- 5000 → 4000자로 조정 (안전 마진 확보)
- 실제 제한(4096)보다 약간 작게 설정

### 구현 변경사항

#### 수정된 파일
1. **`claude_ctb/telegram/bot.py`**
   - `_switch_to_session()` 메서드에 길이 체크 및 분할 로직 추가

2. **`claude_ctb/telegram/message_utils.py`**
   - `safe_send_message()` 개선 - reply_markup 처리
   - 제한값 5000 → 4000 조정
   - 마지막 메시지에만 버튼 표시

### 테스트 결과
```bash
✅ test_message_splitting_utility_exists - PASSED
✅ test_smart_message_splitting_preserves_lines - PASSED
✅ test_markdown_preservation_in_split_messages - PASSED
```

## 💡 사용자 경험 개선

### Before (문제점)
- 세션 전환시 긴 로그 → 에러 발생
- 사용자가 로그를 볼 수 없음
- 짜증나는 에러 메시지

### After (개선됨)
- 긴 로그 자동 분할 전송
- 자연스러운 분할 (줄 단위)
- 연속 메시지 표시로 가독성 유지
- 마지막 메시지에 버튼 유지

## 📈 영향 범위

### 긍정적 영향
1. **안정성 향상**: 메시지 길이 에러 제거
2. **사용성 개선**: 긴 로그도 정상 표시
3. **일관성**: 모든 세션 전환 안정적

### 위험 요소
- 없음 (기존 기능 유지하며 개선만 추가)

## 🔗 관련 파일
- `/home/kyuwon/claude-ctb/claude_ctb/telegram/bot.py`
- `/home/kyuwon/claude-ctb/claude_ctb/telegram/message_utils.py`
- `/home/kyuwon/claude-ctb/tests/test_telegram_message_limits.py`

## ✅ 권장 조치
1. **즉시 배포**: 사용자 경험 즉시 개선
2. **모니터링**: 실제 사용시 분할 빈도 관찰
3. **추가 개선**: 다른 명령어에도 safe_send_message 적용 검토

## 📝 결론

**문제 해결 완료**: 
- "Message too long" 에러 → 자동 분할 전송
- 사용자 친화적 해결책 구현
- 테스트 통과 및 안정성 확보

**핵심 개선**:
- 에러 대신 스마트한 분할
- 자연스러운 메시지 경계
- 버튼 위치 보존