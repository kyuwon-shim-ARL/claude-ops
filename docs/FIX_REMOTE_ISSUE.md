# Git Remote 설정 문제 해결 가이드

## 🚨 문제점

`claude-ops new-project` 명령이 git remote를 설정하지 않아 발생하는 문제:
- 새 프로젝트 생성 시 remote 없음
- 기존 디렉토리 재사용 시 잘못된 remote 사용 위험
- 수동 설정 필요로 실수 가능성

## 🔧 즉시 수정 방법

### 1. 프로젝트 생성 후 항상 확인

```bash
# 프로젝트 생성
claude-ops new-project my-app

# 디렉토리 이동
cd my-app

# remote 확인 (중요!)
git remote -v

# remote가 없다면 설정
git remote add origin git@github.com:USERNAME/REPO.git
```

### 2. 작업 전 체크리스트

```bash
# 필수 확인 사항
pwd                # 현재 위치
git remote -v      # remote 설정
git branch         # 현재 브랜치
git status         # 상태 확인
```

## 🛡️ 예방 스크립트

### safe-git-check.sh

```bash
#!/bin/bash
# 작업 전 git 상태 확인 스크립트

echo "🔍 Git 상태 확인..."
echo "📁 현재 디렉토리: $(pwd)"
echo "🔗 Remote 설정:"
git remote -v

if [ -z "$(git remote -v)" ]; then
    echo "⚠️  경고: Remote가 설정되지 않았습니다!"
    echo "설정 예: git remote add origin git@github.com:USERNAME/REPO.git"
fi
```

## ✅ 문제 해결됨 (2025-09-13)

### 구현된 해결책

project_creator.py가 이제 git remote 미설정 시 명확한 경고를 제공합니다:

1. **자동 경고 시스템**:
   - Git init 후 remote 설정 확인
   - 미설정 시 콘솔에 경고 메시지 표시
   - 프로젝트에 `GIT_REMOTE_NOT_SET.txt` 파일 생성

2. **Pre-push Hook 설치**:
   - `.git/hooks/pre-push` 자동 설치
   - Push 시도 시 remote 미설정 경고
   - Remote 설정 방법 안내

3. **경고 파일 내용**:
   ```
   ⚠️  GIT REMOTE NOT CONFIGURED ⚠️
   =====================================
   
   Your Git repository has been initialized but NO REMOTE is configured.
   This means you cannot push your code to GitHub/GitLab/etc.
   
   TO FIX THIS:
   ------------
   1. Create a repository on GitHub/GitLab/Bitbucket
   2. Add the remote URL to your local repository:
      git remote add origin <your-repo-url>
   3. Verify the remote is set:
      git remote -v
   4. Push your code:
      git push -u origin main
   ```

### 사용자 경험

```bash
# 프로젝트 생성 시
$ claude-ops new-project my-app

✅ Project 'my-app' created successfully!

⚠️  IMPORTANT: Git remote not configured!
   Run: git remote add origin <your-repo-url>
   See GIT_REMOTE_NOT_SET.txt for details

============================================================
⚠️  GIT REMOTE NOT CONFIGURED - ACTION REQUIRED!
============================================================
Your project was created but cannot be pushed to GitHub/GitLab.
To fix this:
  1. Create a repository on GitHub/GitLab
  2. Run: git remote add origin <your-repo-url>
  3. Push: git push -u origin main
============================================================
```

## ⚠️ 주의사항

1. **항상 remote 확인**: 작업 전 `git remote -v` 필수
2. **디렉토리 재사용 금지**: 새 프로젝트는 새 디렉토리에
3. **푸시 전 확인**: `git push --dry-run` 으로 테스트

## 🎯 Action Items

- [ ] project_creator.py에 remote 설정 기능 추가
- [ ] CLI에 --remote 옵션 추가
- [ ] 경고 메시지 강화
- [ ] 문서화 업데이트