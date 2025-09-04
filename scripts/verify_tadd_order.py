#!/usr/bin/env python3
"""
TADD 순서 검증 스크립트
테스트가 구현보다 먼저 작성되었는지 Git 히스토리를 분석하여 검증
"""

import subprocess
import sys
import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple

def run_git_command(cmd: str) -> str:
    """Git 명령어 실행"""
    try:
        result = subprocess.run(
            cmd.split(),
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Git command failed: {e}")
        return ""

def get_pr_commits() -> List[Dict]:
    """PR의 커밋 목록 가져오기"""
    # GitHub Actions 환경에서는 PR 정보 활용
    base_branch = "main"
    
    # 현재 브랜치와 main 사이의 커밋 가져오기
    cmd = f"git log {base_branch}..HEAD --pretty=format:%H|||%s|||%ai"
    output = run_git_command(cmd)
    
    if not output:
        return []
    
    commits = []
    for line in output.split('\n'):
        if line:
            hash_val, message, timestamp = line.split('|||')
            commits.append({
                'hash': hash_val,
                'message': message,
                'timestamp': datetime.fromisoformat(timestamp.replace(' +', '+'))
            })
    
    return commits

def categorize_commit(commit: Dict) -> str:
    """커밋 메시지로 커밋 타입 분류"""
    message = commit['message'].lower()
    
    if message.startswith('test:') or 'test' in message:
        return 'test'
    elif message.startswith('feat:') or message.startswith('fix:'):
        return 'implementation'
    else:
        return 'other'

def extract_feature_name(commit: Dict) -> Optional[str]:
    """커밋 메시지에서 기능명 추출"""
    message = commit['message']
    
    # conventional commit에서 기능명 추출
    if ':' in message:
        parts = message.split(':', 1)
        if len(parts) > 1:
            # 괄호 안의 스코프 또는 전체 설명을 기능명으로
            feature = parts[1].strip()
            # 특수문자 제거
            feature = feature.replace('(', '').replace(')', '')
            return feature.lower()[:30]  # 최대 30자
    
    return None

def find_test_and_impl_pairs(commits: List[Dict]) -> List[Tuple[Dict, Dict]]:
    """테스트와 구현 커밋 쌍 찾기"""
    pairs = []
    
    # 기능별로 그룹화
    features = {}
    for commit in commits:
        feature = extract_feature_name(commit)
        if feature:
            if feature not in features:
                features[feature] = {'test': None, 'impl': None}
            
            commit_type = categorize_commit(commit)
            if commit_type == 'test' and not features[feature]['test']:
                features[feature]['test'] = commit
            elif commit_type == 'implementation' and not features[feature]['impl']:
                features[feature]['impl'] = commit
    
    # 쌍으로 묶기
    for feature, commits_dict in features.items():
        if commits_dict['test'] and commits_dict['impl']:
            pairs.append((commits_dict['test'], commits_dict['impl']))
    
    return pairs

def verify_test_first(test_commit: Dict, impl_commit: Dict) -> bool:
    """테스트가 구현보다 먼저 작성되었는지 확인"""
    return test_commit['timestamp'] < impl_commit['timestamp']

def check_test_initially_fails(test_commit: Dict) -> bool:
    """테스트가 처음에 실패했는지 확인 (CI 로그 분석)"""
    # 실제 구현에서는 CI 로그를 분석
    # 여기서는 간단히 구현
    hash_val = test_commit['hash']
    
    # 해당 커밋 시점의 테스트 실행 시뮬레이션
    # GitHub Actions 환경에서는 artifacts나 로그에서 확인
    return True  # 임시로 True 반환

def main():
    """메인 검증 로직"""
    print("🔍 TADD Order Verification Starting...")
    print("-" * 50)
    
    commits = get_pr_commits()
    
    if not commits:
        print("⚠️  No commits found in PR")
        return 0
    
    print(f"📊 Found {len(commits)} commits to analyze")
    
    # 테스트-구현 쌍 찾기
    pairs = find_test_and_impl_pairs(commits)
    
    if not pairs:
        print("⚠️  No test-implementation pairs found")
        print("💡 Make sure to use conventional commit messages:")
        print("   - test: <description> for tests")
        print("   - feat: <description> for features")
        return 0
    
    print(f"\n🔗 Found {len(pairs)} test-implementation pairs")
    print("-" * 50)
    
    violations = []
    warnings = []
    
    for test_commit, impl_commit in pairs:
        feature = extract_feature_name(test_commit) or "unknown"
        
        print(f"\n📦 Feature: {feature}")
        print(f"   Test:  {test_commit['message'][:50]}")
        print(f"   Impl:  {impl_commit['message'][:50]}")
        
        # 순서 검증
        if verify_test_first(test_commit, impl_commit):
            print(f"   ✅ Test written before implementation")
            
            # 초기 실패 검증
            if not check_test_initially_fails(test_commit):
                warning = f"Test might not have failed initially: {feature}"
                warnings.append(warning)
                print(f"   ⚠️  {warning}")
        else:
            violation = f"Implementation before test: {feature}"
            violations.append(violation)
            print(f"   ❌ {violation}")
    
    # 결과 요약
    print("\n" + "=" * 50)
    print("📊 TADD Compliance Summary")
    print("=" * 50)
    
    if violations:
        print(f"\n❌ VIOLATIONS ({len(violations)}):")
        for v in violations:
            print(f"   - {v}")
        
        print("\n🚫 TADD Order Check: FAILED")
        print("💡 Fix: Write tests before implementation")
        return 1
    
    if warnings:
        print(f"\n⚠️  WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"   - {w}")
    
    print("\n✅ TADD Order Check: PASSED")
    print("🎉 All tests were written before implementation!")
    
    # GitHub Actions 출력
    if violations:
        print(f"::error::TADD violations found: {len(violations)}")
    elif warnings:
        print(f"::warning::TADD warnings: {len(warnings)}")
    
    return 0 if not violations else 1

if __name__ == "__main__":
    sys.exit(main())