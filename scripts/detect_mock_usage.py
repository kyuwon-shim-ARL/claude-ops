#!/usr/bin/env python3
"""
Mock 사용률 검사 스크립트
테스트 코드에서 Mock 사용률을 분석하고 제한을 강제
"""

import ast
import sys
from pathlib import Path
from typing import Dict, List, Set

class MockDetector(ast.NodeVisitor):
    """AST를 순회하며 Mock 사용 패턴 검출"""
    
    def __init__(self):
        self.mock_imports: Set[str] = set()
        self.mock_usages: List[Dict] = []
        self.test_methods: List[str] = []
        self.current_test = None
        
    def visit_Import(self, node):
        """import 문 분석"""
        for alias in node.names:
            if 'mock' in alias.name.lower() or 'Mock' in alias.name:
                self.mock_imports.add(alias.name)
        self.generic_visit(node)
        
    def visit_ImportFrom(self, node):
        """from ... import 문 분석"""
        if node.module and ('mock' in node.module.lower() or 'unittest.mock' in node.module):
            for alias in node.names:
                self.mock_imports.add(alias.name)
        self.generic_visit(node)
        
    def visit_FunctionDef(self, node):
        """테스트 함수 검출"""
        if node.name.startswith('test_'):
            self.test_methods.append(node.name)
            self.current_test = node.name
            
            # 데코레이터 확인 (@patch, @mock 등)
            for decorator in node.decorator_list:
                if self._is_mock_decorator(decorator):
                    self.mock_usages.append({
                        'test': node.name,
                        'type': 'decorator',
                        'line': node.lineno
                    })
        
        self.generic_visit(node)
        self.current_test = None
    
    def visit_Call(self, node):
        """함수 호출 분석"""
        if self.current_test:
            func_name = self._get_call_name(node)
            
            # Mock 관련 호출 검출
            if func_name and any(mock in func_name for mock in ['Mock', 'MagicMock', 'patch', 'mock']):
                self.mock_usages.append({
                    'test': self.current_test,
                    'type': 'call',
                    'line': node.lineno,
                    'name': func_name
                })
        
        self.generic_visit(node)
    
    def _is_mock_decorator(self, decorator) -> bool:
        """데코레이터가 Mock 관련인지 확인"""
        if isinstance(decorator, ast.Name):
            return 'patch' in decorator.id or 'mock' in decorator.id.lower()
        elif isinstance(decorator, ast.Attribute):
            return 'patch' in decorator.attr or 'mock' in decorator.attr.lower()
        elif isinstance(decorator, ast.Call):
            return self._is_mock_decorator(decorator.func)
        return False
    
    def _get_call_name(self, node) -> str:
        """함수 호출의 이름 추출"""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            return node.func.attr
        return ""

def analyze_test_file(filepath: Path) -> Dict:
    """단일 테스트 파일 분석"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    try:
        tree = ast.parse(content)
        detector = MockDetector()
        detector.visit(tree)
        
        return {
            'file': str(filepath),
            'total_tests': len(detector.test_methods),
            'mock_imports': len(detector.mock_imports),
            'mock_usages': detector.mock_usages,
            'tests_with_mock': len(set(u['test'] for u in detector.mock_usages)),
            'test_methods': detector.test_methods
        }
    except SyntaxError as e:
        print(f"⚠️  Syntax error in {filepath}: {e}")
        return None

def find_test_files(root_dir: str = ".") -> List[Path]:
    """테스트 파일 찾기"""
    test_files = []
    
    for pattern in ["**/test_*.py", "**/tests/*.py", "**/*_test.py"]:
        test_files.extend(Path(root_dir).glob(pattern))
    
    # 중복 제거
    return list(set(test_files))

def categorize_mock_usage(mock_usage: Dict, file_content: str) -> str:
    """Mock 사용을 카테고리로 분류"""
    # 간단한 휴리스틱 기반 분류
    name = mock_usage.get('name', '').lower()
    
    if any(ext in name for ext in ['request', 'http', 'api', 'client']):
        return 'external_service'
    elif any(db in name for db in ['database', 'db', 'model', 'query']):
        return 'database'
    elif any(fs in name for fs in ['file', 'open', 'path', 'os']):
        return 'filesystem'
    else:
        return 'internal_logic'

def generate_report(results: List[Dict]) -> Dict:
    """전체 분석 결과 리포트 생성"""
    total_tests = sum(r['total_tests'] for r in results if r)
    tests_with_mock = sum(r['tests_with_mock'] for r in results if r)
    total_mock_usages = sum(len(r['mock_usages']) for r in results if r)
    
    mock_percentage = (tests_with_mock / total_tests * 100) if total_tests > 0 else 0
    
    # Mock 사용 카테고리별 분류
    categories = {
        'external_service': 0,
        'database': 0,
        'filesystem': 0,
        'internal_logic': 0
    }
    
    violations = []
    
    for result in results:
        if not result:
            continue
            
        for usage in result['mock_usages']:
            # 파일 내용을 읽어서 카테고리 분류 (실제 구현에서는 더 정교하게)
            category = 'internal_logic'  # 기본값
            
            if category == 'internal_logic':
                violations.append({
                    'file': result['file'],
                    'test': usage['test'],
                    'line': usage['line'],
                    'reason': 'Mocking internal logic is not allowed'
                })
            
            categories[category] += 1
    
    return {
        'total_tests': total_tests,
        'tests_with_mock': tests_with_mock,
        'mock_percentage': mock_percentage,
        'total_mock_usages': total_mock_usages,
        'categories': categories,
        'violations': violations,
        'files_analyzed': len(results)
    }

def main():
    """메인 실행 함수"""
    print("🔍 Mock Usage Detection Starting...")
    print("-" * 50)
    
    # 테스트 파일 찾기
    test_files = find_test_files()
    
    if not test_files:
        print("⚠️  No test files found")
        return 0
    
    print(f"📊 Found {len(test_files)} test files to analyze")
    
    # 각 파일 분석
    results = []
    for test_file in test_files:
        result = analyze_test_file(test_file)
        if result:
            results.append(result)
            if result['mock_usages']:
                print(f"   📄 {test_file.name}: {result['tests_with_mock']}/{result['total_tests']} tests use mocks")
    
    # 리포트 생성
    report = generate_report(results)
    
    # 결과 출력
    print("\n" + "=" * 50)
    print("📊 Mock Usage Analysis Report")
    print("=" * 50)
    
    print("\n📈 Overall Statistics:")
    print(f"   Total test methods: {report['total_tests']}")
    print(f"   Tests using mocks: {report['tests_with_mock']}")
    print(f"   Mock usage rate: {report['mock_percentage']:.1f}%")
    print(f"   Total mock usages: {report['total_mock_usages']}")
    
    print("\n📦 Mock Categories:")
    for category, count in report['categories'].items():
        emoji = "✅" if category != 'internal_logic' else "❌"
        print(f"   {emoji} {category}: {count}")
    
    # 제한 확인
    MAX_MOCK_PERCENTAGE = 20
    
    if report['mock_percentage'] > MAX_MOCK_PERCENTAGE:
        print("\n❌ MOCK USAGE VIOLATION")
        print(f"   Current: {report['mock_percentage']:.1f}%")
        print(f"   Limit: {MAX_MOCK_PERCENTAGE}%")
        print(f"   Reduce mock usage by {report['mock_percentage'] - MAX_MOCK_PERCENTAGE:.1f}%")
        
        if report['violations']:
            print(f"\n🚫 Internal Logic Mocking Detected ({len(report['violations'])} violations):")
            for v in report['violations'][:5]:  # 최대 5개만 표시
                print(f"   - {v['file']}:{v['line']} in {v['test']}")
        
        print("\n💡 Recommendations:")
        print("   1. Use real implementations instead of mocks")
        print("   2. Mock only external services (APIs, databases)")
        print("   3. Use test doubles sparingly")
        print("   4. Consider integration tests over unit tests with mocks")
        
        return 1
    
    print("\n✅ Mock Usage Check: PASSED")
    print(f"   Mock usage ({report['mock_percentage']:.1f}%) is within limit ({MAX_MOCK_PERCENTAGE}%)")
    
    # GitHub Actions 출력
    if report['mock_percentage'] > MAX_MOCK_PERCENTAGE:
        print(f"::error::Mock usage {report['mock_percentage']:.1f}% exceeds limit {MAX_MOCK_PERCENTAGE}%")
    elif report['mock_percentage'] > MAX_MOCK_PERCENTAGE * 0.8:
        print(f"::warning::Mock usage {report['mock_percentage']:.1f}% approaching limit {MAX_MOCK_PERCENTAGE}%")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())