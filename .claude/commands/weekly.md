# /주간보고 - PRD 기반 전체 프로젝트 진행 보고

## 명령어 개요
모든 프로젝트의 진행 상황을 PRD와 로드맵 기준으로 종합 분석하여 보고

## 사용법
```
/주간보고
/주간보고 --include-archived  # 완료된 프로젝트 포함
```

## Claude 실행 프로세스

### 1단계: 모든 프로젝트 스캔
```python
def scan_all_projects():
    projects = []
    # projects/ 폴더의 모든 하위 디렉토리 검색
    for project_dir in glob("projects/*"):
        if has_prd(project_dir):
            projects.append({
                "name": project_name,
                "prd": read_prd(project_dir),
                "roadmap": read_roadmap(project_dir),
                "documents": scan_documents(project_dir)
            })
    return projects
```

### 2단계: PRD 기반 진행률 분석
```python
def analyze_progress(project):
    # PRD의 요구사항과 현재 상태 비교
    prd_requirements = extract_requirements(project["prd"])
    completed = []
    in_progress = []
    pending = []
    
    for req in prd_requirements:
        status = check_implementation_status(req, project["documents"])
        if status == "complete":
            completed.append(req)
        elif status == "in_progress":
            in_progress.append(req)
        else:
            pending.append(req)
    
    # Mock vs 실제 구현 구분
    real_implementations = filter_real_implementations(completed)
    mock_implementations = filter_mock_implementations(completed)
    
    return {
        "completion_rate": len(completed) / len(prd_requirements) * 100,
        "real_progress": len(real_implementations) / len(prd_requirements) * 100,
        "current_phase": identify_current_phase(project["roadmap"]),
        "velocity": calculate_weekly_velocity(project),
        "blockers": identify_blockers(in_progress)
    }
```

### 3단계: 계획과 도움 구분
```python
def categorize_next_actions(projects):
    self_resolvable = []  # 자체 해결 가능
    need_help = []        # 외부 지원 필요
    
    for project in projects:
        for task in project["next_tasks"]:
            if can_self_resolve(task):
                self_resolvable.append({
                    "project": project["name"],
                    "task": task,
                    "command": suggest_command(task),
                    "estimated_time": estimate_time(task)
                })
            else:
                need_help.append({
                    "project": project["name"],
                    "issue": task["blocker"],
                    "required_support": task["help_needed"],
                    "impact": assess_impact(task)
                })
    
    return self_resolvable, need_help
```

### 4단계: 보고서 생성
```python
def generate_weekly_report(date):
    report_path = f"docs/CURRENT/weekly_report_{date}.md"
    
    # 보고서 템플릿에 데이터 채우기
    report = f"""# 주간 진행 보고서
*{date} | PRD 기반 진행 현황*

## 🎯 전체 현황
- 관리 중인 프로젝트: {total_projects}개
- 평균 진행률: {avg_completion}%
- 이번 주 velocity: {weekly_velocity}

## 📊 프로젝트별 상황

{for project in projects:
    ### {project.name}
    **WHY**: {project.purpose}
    **로드맵 위치**: {project.current_phase} / {project.total_phases}
    **진행률**: {project.completion_rate}% (실제: {project.real_progress}%)
    
    ```
    {visualize_roadmap_progress(project)}
    ```
    
    **이번 주 성과**:
    {list_weekly_achievements(project)}
    
    **블로커**:
    {list_blockers(project)}
}

## 📋 실행 계획 (자체 해결 가능)

{for task in self_resolvable:
    - [ ] [{task.project}] {task.description}
          명령어: `{task.command}`
          예상 시간: {task.estimated_time}
}

## 🆘 필요한 도움 (외부 지원 필요)

{for issue in need_help:
    ### [{issue.project}] {issue.title}
    - **문제**: {issue.description}
    - **필요한 지원**: {issue.required_support}
    - **영향도**: {issue.impact}
}

## 📈 진행률 대시보드

### 속도 메트릭
| 메트릭 | 이번 주 | 지난 주 | 변화 |
|--------|---------|---------|------|
| 완료 작업 | {this_week_completed} | {last_week_completed} | {change}% |
| 코드 라인 | {loc_added} | {loc_added_last} | {loc_change}% |
| 문서 생성 | {docs_created} | {docs_created_last} | {docs_change}% |

### 우선순위 매트릭스
| Priority | Must Have | Should Have | Nice to Have |
|----------|-----------|-------------|--------------|
| 이번 주 | {must_tasks} | {should_tasks} | {nice_tasks} |
| 다음 주 | {next_must} | {next_should} | {next_nice} |

## 💡 주요 인사이트

{generate_insights(projects)}

## 🎯 다음 주 목표

{for project in projects:
    - **{project.name}**: {project.next_milestone}
}

---
*생성 시각: {timestamp}*
*다음 보고: {next_report_date}*
"""
    
    # 파일 저장
    write_file(report_path, report)
    return report_path
```

## 실제 실행 예시

### 입력:
```
/주간보고
```

### Claude 실행:
1. projects/ 폴더의 모든 프로젝트 스캔
2. 각 프로젝트의 PRD와 현재 상태 비교
3. 진행률과 velocity 계산
4. 자체 해결 가능한 작업과 도움 필요한 사항 분류
5. 종합 보고서 생성

### 출력 예시:
```markdown
# 주간 진행 보고서
*2024-01-26 | PRD 기반 진행 현황*

## 🎯 전체 현황
- 관리 중인 프로젝트: 3개
- 평균 진행률: 68%
- 이번 주 velocity: 12 story points

## 📊 프로젝트별 상황

### RNA-seq-drug-response
**WHY**: 약물 반응성 바이오마커 발굴
**로드맵 위치**: 분석 단계 (4/6)
**진행률**: 65% (실제: 60%, Mock: 5%)

```
[✓] 가설 → [✓] 설계 → [✓] 데이터 수집 → [▶] 분석 → [ ] 검증 → [ ] 논문
                                                   ↑ 현재 위치
```

**이번 주 성과**:
- DEG 분석 완료 (2,341개 유전자)
- Pathway enrichment 분석 완료
- 히트맵 시각화 완성

**블로커**:
- GPU 서버 접근 권한 필요 (딥러닝 모델 학습)

## 📋 실행 계획 (자체 해결 가능)

- [ ] [RNA-seq] qPCR validation 프라이머 설계
      명령어: `/구현 "qPCR 프라이머 설계 스크립트"`
      예상 시간: 2시간

- [ ] [Proteomics] 품질 관리 보고서 작성
      명령어: `/분석 "QC 메트릭 분석"`
      예상 시간: 1시간

## 🆘 필요한 도움 (외부 지원 필요)

### [RNA-seq] GPU 서버 접근 권한
- **문제**: 딥러닝 모델 학습을 위한 GPU 필요
- **필요한 지원**: IT 팀에 서버 접근 권한 요청
- **영향도**: 높음 (일정 지연 가능)

## 📈 진행률 대시보드

### 속도 메트릭
| 메트릭 | 이번 주 | 지난 주 | 변화 |
|--------|---------|---------|------|
| 완료 작업 | 8 | 6 | +33% |
| 코드 라인 | 1,250 | 890 | +40% |
| 문서 생성 | 5 | 3 | +67% |

## 💡 주요 인사이트

1. **생산성 향상**: 자동화 도구 도입으로 분석 속도 40% 개선
2. **품질 이슈**: Mock 테스트 비율 감소 중 (15% → 5%)
3. **리스크**: GPU 서버 미확보 시 2주 지연 예상

## 🎯 다음 주 목표

- **RNA-seq**: qPCR validation 완료
- **Proteomics**: 1차 분석 결과 도출
- **Clinical**: IRB 승인 획득

---
*생성 시각: 2024-01-26 18:00*
*다음 보고: 2024-02-02*
```

## 주요 기능

### 자동 분석
- PRD 요구사항 충족도 측정
- Mock vs 실제 구현 구분
- 진행 속도(velocity) 계산
- 블로커 자동 감지

### 인사이트 도출
- 생산성 트렌드 분석
- 리스크 조기 감지
- 개선 기회 식별

### 액션 아이템 생성
- 구체적 명령어 제시
- 시간 추정
- 우선순위 자동 설정

## 효과

1. **투명성**: 모든 프로젝트 상태 한눈에 파악
2. **예측성**: 속도 기반 완료 시점 예측
3. **실행력**: 구체적 다음 단계 제시
4. **협업**: 필요한 도움 명확히 정의

## 워크플로우 통합

```bash
# 매주 금요일 실행 권장
/문서정리        # 개별 프로젝트 정리
     ↓
/주간보고        # 전체 프로젝트 종합
     ↓
경영진/팀 공유    # 투명한 진행 상황 공유
```

---
*PRD 기반으로 실제 진행 상황을 정확히 추적합니다.*