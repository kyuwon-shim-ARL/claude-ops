# /분석 - 자동 저장 분석 명령어 v4.0

## 명령어 개요
분석 요청 → 자동 수행 → **파일로 자동 저장** → 경로 알림

## 사용법
```
/분석 "분석하고 싶은 내용"
```

## Claude 실행 프로세스 (자동 저장 포함)

### 1단계: 분석 수행
```python
def perform_analysis(request):
    # 분석 유형 자동 판단
    analysis_type = detect_type(request)
    
    # 분석 실행
    results = analyze(request, analysis_type)
    
    return results
```

### 2단계: 마크다운 문서 생성
```python
def create_document(request, results):
    doc = f"""# {extract_title(request)}

## 📅 분석 정보
- **날짜**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
- **요청**: {request}
- **유형**: {analysis_type}

## 📊 분석 결과
{results}

## 💾 관련 파일
- 데이터: {data_paths if exists}
- 코드: {code_paths if exists}

## 🔗 관련 분석
- {find_related_analyses()}
"""
    return doc
```

### 3단계: 자동 저장 (핵심!)
```python
def auto_save_analysis(doc, request):
    # 파일명 생성: 날짜-핵심키워드
    date_str = datetime.now().strftime('%Y-%m-%d')
    title = extract_keywords(request)[:30]
    filename = f"{date_str}-{title}.md"
    
    # 저장 경로
    filepath = f"docs/analysis/{filename}"
    
    # Write 도구로 실제 저장
    write_file(filepath, doc)
    
    # 인덱스 업데이트
    update_index(filepath, title)
    
    return filepath
```

### 4단계: 사용자 알림
```python
def notify_user(filepath):
    print(f"""
✅ 분석 완료 및 자동 저장됨
📁 저장 위치: {filepath}
🔍 다시 보기: cat {filepath}
""")
```

## 실제 실행 예시

### 사용자 입력:
```
/분석 "최근 API 응답시간이 느려진 원인 분석"
```

### Claude 실행:
1. API 로그 분석
2. 성능 메트릭 수집
3. 병목 지점 식별
4. 분석 결과 정리
5. **자동으로 파일 저장**: `docs/analysis/2024-01-20-API응답시간분석.md`
6. 사용자에게 알림:
```
✅ 분석 완료 및 자동 저장됨
📁 저장 위치: docs/analysis/2024-01-20-API응답시간분석.md
🔍 다시 보기: cat docs/analysis/2024-01-20-API응답시간분석.md
```

## 저장되는 파일 구조

```markdown
# API 응답시간 분석

## 📅 분석 정보
- **날짜**: 2024-01-20 14:30
- **요청**: 최근 API 응답시간이 느려진 원인 분석
- **유형**: performance

## 📊 분석 결과

### 주요 발견사항
1. DB 쿼리 최적화 필요 (N+1 문제)
   - /api/users 엔드포인트: 평균 2.3s → 0.3s 예상
2. 캐시 미적용 구간 발견
   - 정적 데이터 캐싱 시 50% 개선 가능
3. 불필요한 미들웨어 체이닝
   - 3개 미들웨어 제거 가능

### 성능 측정값
- 현재 평균 응답시간: 1.8s
- P95: 3.2s  
- P99: 5.1s

### 권장 조치
1. DB 인덱스 추가
2. Redis 캐시 구현
3. 미들웨어 리팩토링

## 💾 관련 파일
- 로그: logs/api/2024-01-20.log
- 메트릭: metrics/performance/

## 🔗 관련 분석
- [2024-01-15-DB쿼리최적화.md](2024-01-15-DB쿼리최적화.md)
```

## 인덱스 자동 업데이트

### docs/analysis/index.md (자동 생성)
```markdown
# 분석 보고서 인덱스

## 최근 분석
- 2024-01-20: [API 응답시간 분석](2024-01-20-API응답시간분석.md)
- 2024-01-19: [메모리 누수 조사](2024-01-19-메모리누수조사.md)
- 2024-01-18: [사용자 행동 패턴](2024-01-18-사용자행동패턴.md)

## 카테고리별
### Performance
- API 응답시간 분석
- 메모리 누수 조사

### User Analytics  
- 사용자 행동 패턴
```

## 장점

1. **영구 보존**: 분석 결과가 파일로 저장되어 영구 보존
2. **자동화**: 사용자가 따로 저장 명령 불필요
3. **체계적**: 일관된 형식과 구조
4. **검색 가능**: 파일명과 인덱스로 쉽게 찾기
5. **공유 가능**: 마크다운 파일로 누구나 읽기 가능

## 핵심 차별점

**기존 방식**:
```
/분석 "..." → 대화창 출력 → 끝
```

**새로운 방식**:
```
/분석 "..." → 대화창 출력 + 자동 파일 저장 + 인덱스 업데이트
```

사용자는 똑같이 사용하지만, 결과는 자동으로 영구 보존됩니다!