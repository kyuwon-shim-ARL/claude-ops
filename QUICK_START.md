# 🚀 Claude Code 워크플로우 빠른 시작 가이드

이 가이드는 repository clone 후 **5분 이내**에 완벽한 워크플로우를 사용할 수 있도록 설계되었습니다.

## ⚡ 빠른 시작 (5분)

### 1단계: 환경 설정 (2분)

```bash
# 1. Repository clone 후 이동
git clone <your-repo-url>
cd MC_test_ops

# 2. 의존성 설치
uv sync
# 또는 pip install -r requirements.txt

# 3. 환경 변수 설정
cp .env.example .env
# .env 파일을 열어서 실제 값으로 수정:
```

**.env 설정 (필수):**
```bash
# Notion API 설정
NOTION_API_KEY=secret_your_notion_integration_token
NOTION_TASKS_DB_ID=your_tasks_database_id
NOTION_PROJECTS_DB_ID=your_projects_database_id
NOTION_KNOWLEDGE_HUB_ID=your_knowledge_hub_page_id

# GitHub API 설정  
GITHUB_PAT=ghp_your_github_personal_access_token
GITHUB_REPO_OWNER=your-github-username
GITHUB_REPO_NAME=your-repo-name
```

### 2단계: 첫 프로젝트 생성 (1분)

```bash
# 기본 제공되는 개선된 프로젝트 계획으로 티켓 생성
/project-plan docs/proposals/2025-07-24_improved-data-analysis-pipeline.md
```

**결과:** 9개의 구체적인 Task가 Notion에 생성됨

### 3단계: 첫 Task 실행 (2분)

```bash  
# 1. 첫 번째 Task 시작
/task-start <생성된-TID>

# 2. 작업 수행 (예시: 간단한 파일 생성)
echo "# My Implementation" > my_implementation.py

# 3. 완전 자동화 완료
/task-finish <TID> --pr --auto-merge
```

## 🎯 핵심 기능 즉시 사용

### A. 완전 자동화 워크플로우
```bash
/task-start <TID>           # Task 시작 + Git 브랜치 생성
# ... 작업 수행 ...
/task-finish <TID> --pr --auto-merge  # PR 생성 + 자동 merge + 정리
```

### B. 대화 아카이빙 (구조화된 요약)
```bash
/task-archive              # 현재 브랜치에서 자동 감지
/task-archive <TID>         # 특정 Task 지정
```

### C. Git LFS 자동 추적
- `*.txt`, `*.csv`, `*.tsv` 파일 자동 추적
- 결과물이 자동으로 버전 관리됨

## 🔧 설정 세부사항

### Notion 설정

1. **Notion Integration 생성:**
   - https://www.notion.so/my-integrations
   - "New integration" 클릭
   - API 키 복사 → `.env`의 `NOTION_API_KEY`

2. **Database ID 찾기:**
   - Tasks Database URL: `notion.so/.../{DATABASE_ID}`
   - URL에서 32자리 ID 복사

3. **Database 권한 부여:**
   - Tasks, Projects Database에 Integration 초대
   - "Share" → Integration 이름 선택

### GitHub 설정

1. **Personal Access Token 생성:**
   - GitHub → Settings → Developer settings → Personal access tokens
   - "Generate new token" (classic)
   - Scopes: `repo`, `workflow` 선택
   - 토큰 복사 → `.env`의 `GITHUB_PAT`

### Git LFS 설정 (자동)

```bash
# 이미 설정되어 있음 (.gitattributes)
*.txt filter=lfs diff=lfs merge=lfs -text
*.csv filter=lfs diff=lfs merge=lfs -text  
*.tsv filter=lfs diff=lfs merge=lfs -text
```

## 🎪 실제 사용 예시

### 시나리오: 데이터 분석 모듈 구현

```bash
# 1. Task 시작
/task-start 23a5d36f-fc73-81ff-xxxx  # 실제 생성된 TID 사용

# 2. 구현 작업
cat > src/modules/my_analysis.py << 'EOF'
def analyze_data(data):
    """데이터 분석 함수"""
    return {"mean": data.mean(), "std": data.std()}
EOF

# 3. 테스트 작성
cat > test_analysis.py << 'EOF'  
import pandas as pd
from src.modules.my_analysis import analyze_data

data = pd.Series([1, 2, 3, 4, 5])
result = analyze_data(data)
print(f"Analysis result: {result}")
EOF

# 4. 실행 및 결과 생성
python test_analysis.py > analysis_results.txt

# 5. 완전 자동화 완료
/task-finish <TID> --pr --auto-merge
```

**결과:**
- ✅ PR 자동 생성 및 merge  
- ✅ `analysis_results.txt` Git LFS 추적
- ✅ Notion Task 상태 "Done"으로 업데이트
- ✅ 구조화된 대화 요약 Notion에 저장
- ✅ 브랜치 자동 정리

## 🛡️ 문제 해결

### 환경 변수 확인
```bash
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
print('Notion API:', 'OK' if os.getenv('NOTION_API_KEY') else 'MISSING')
print('GitHub PAT:', 'OK' if os.getenv('GITHUB_PAT') else 'MISSING')
"
```

### 의존성 확인  
```bash
uv run python -c "
import notion_client, github, pandas
print('All dependencies installed successfully!')
"
```

### 워크플로우 테스트
```bash
# 간단한 테스트 실행
python src/workflow_manager.py --help
```

## 📚 고급 기능

### 커스텀 프로젝트 계획
```bash
# 자신만의 프로젝트 계획 작성
cp docs/proposals/2025-07-24_improved-data-analysis-pipeline.md docs/proposals/my-project.md
# ... 내용 수정 ...
/project-plan docs/proposals/my-project.md
```

### 배치 작업
```bash
# 여러 Task 연속 실행
for tid in TID1 TID2 TID3; do
    /task-start $tid
    # ... 작업 수행 ...
    /task-finish $tid --pr --auto-merge
done
```

---

## 🎉 완료!

이제 당신은 **완전 자동화된 연구 워크플로우**를 사용할 수 있습니다:

- 🎯 **명확한 목표와 산출물**을 가진 Task들
- 🔄 **완전 자동화**된 Git 워크플로우  
- 📋 **구조화된 문서화** (Notion 연동)
- 📊 **자동 결과물 추적** (Git LFS)
- 🧹 **깔끔한 브랜치 관리**

**다음 단계:** 원하는 Task를 선택해서 `/task-start`로 시작하세요! 🚀