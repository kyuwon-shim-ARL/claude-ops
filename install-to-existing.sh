#!/bin/bash

# Claude Code 워크플로우를 기존 프로젝트에 설치하는 스크립트
# Usage: curl -sSL https://raw.githubusercontent.com/kyuwon-shim-ARL/claude-ops/main/install-to-existing.sh | bash

set -e

echo "🚀 Claude Code 워크플로우를 기존 프로젝트에 설치합니다..."

# 현재 디렉토리가 Git 저장소인지 확인
if [ ! -d ".git" ]; then
    echo "❌ 현재 디렉토리가 Git 저장소가 아닙니다."
    echo "💡 Git 저장소 루트에서 실행해주세요."
    exit 1
fi

# 임시 디렉토리 생성
TEMP_DIR=$(mktemp -d)
echo "📂 임시 디렉토리: $TEMP_DIR"

# Claude Code 워크플로우 다운로드
echo "⬇️  워크플로우 파일들을 다운로드 중..."
git clone --depth 1 https://github.com/kyuwon-shim-ARL/claude-ops.git "$TEMP_DIR/claude-ops"

# 백업 확인
echo "💾 기존 파일 백업을 원하시나요? (y/N)"
read -r backup_choice
if [[ $backup_choice =~ ^[Yy]$ ]]; then
    BACKUP_DIR="./backup-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    echo "📦 백업 디렉토리: $BACKUP_DIR"
fi

# 핵심 파일들 복사
echo "📁 핵심 워크플로우 파일들을 설치 중..."

# CLAUDE.md
if [ -f "CLAUDE.md" ] && [[ $backup_choice =~ ^[Yy]$ ]]; then
    cp CLAUDE.md "$BACKUP_DIR/"
fi
cp "$TEMP_DIR/claude-ops/CLAUDE.md" .
echo "✅ CLAUDE.md 설치 완료"

# .env.example
if [ -f ".env.example" ] && [[ $backup_choice =~ ^[Yy]$ ]]; then
    cp .env.example "$BACKUP_DIR/"
fi
cp "$TEMP_DIR/claude-ops/.env.example" .
echo "✅ .env.example 설치 완료"

# slash_commands 디렉토리
if [ -d "slash_commands" ] && [[ $backup_choice =~ ^[Yy]$ ]]; then
    cp -r slash_commands "$BACKUP_DIR/"
fi
rm -rf slash_commands
cp -r "$TEMP_DIR/claude-ops/slash_commands" .
echo "✅ slash_commands 디렉토리 설치 완료"

# src 디렉토리 처리
mkdir -p src
if [ -f "src/workflow_manager.py" ] && [[ $backup_choice =~ ^[Yy]$ ]]; then
    cp src/workflow_manager.py "$BACKUP_DIR/"
fi
cp "$TEMP_DIR/claude-ops/src/workflow_manager.py" src/
echo "✅ workflow_manager.py 설치 완료"

# Git LFS 설정
if [ -f ".gitattributes" ]; then
    if [[ $backup_choice =~ ^[Yy]$ ]]; then
        cp .gitattributes "$BACKUP_DIR/"
    fi
    # 기존 .gitattributes에 LFS 설정 추가
    echo "" >> .gitattributes
    echo "# Claude Code 워크플로우 - Git LFS 설정" >> .gitattributes
    cat "$TEMP_DIR/claude-ops/.gitattributes" >> .gitattributes
else
    cp "$TEMP_DIR/claude-ops/.gitattributes" .
fi
echo "✅ Git LFS 설정 완료"

# Python 의존성 정보 복사 (병합용)
cp "$TEMP_DIR/claude-ops/pyproject.toml" ./claude-ops-dependencies.toml
echo "✅ Python 의존성 정보 복사 완료 (claude-ops-dependencies.toml)"

# 임시 파일 정리
rm -rf "$TEMP_DIR"

echo ""
echo "🎉 Claude Code 워크플로우가 성공적으로 설치되었습니다!"
echo ""
echo "📋 다음 단계:"
echo "1. .env 파일 설정: cp .env.example .env && vi .env"
echo "2. Python 의존성 추가: claude-ops-dependencies.toml 참조하여 pyproject.toml 업데이트"
echo "3. Git LFS 초기화: git lfs install"
echo "4. 첫 프로젝트 생성: echo '# My Project' > docs/my-project.md && /project-plan docs/my-project.md"
echo ""
if [[ $backup_choice =~ ^[Yy]$ ]]; then
    echo "💾 백업 파일들이 $BACKUP_DIR 에 저장되었습니다."
fi
echo "📖 자세한 사용법: https://github.com/kyuwon-shim-ARL/claude-ops"