#!/usr/bin/env python3
"""
Mock 사용률 검사 스크립트
테스트 코드에서 Mock 사용률을 분석하고 제한을 강제
"""

import ast
import os
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

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
                    mock_target = self._extract_mock_target(decorator)
                    self.mock_usages.append({
                        'test': node.name,
                        'type': 'decorator',
                        'line': node.lineno,
                        'mock_target': mock_target
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
    
    def _extract_mock_target(self, decorator) -> str:
        """데코레이터에서 mock 대상 추출"""
        if isinstance(decorator, ast.Call):
            if decorator.args:
                arg = decorator.args[0]
                if isinstance(arg, ast.Constant):
                    return arg.value
                elif isinstance(arg, ast.Str):  # Python 3.7 compatibility
                    return arg.s
        return ""
    
    def _get_call_name(self, node) -> str:
        """함수 호출의 이름 추출"""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            return node.func.attr
        return ""

def analyze_test_file(filepath: Path) -> Dict:
    """Analyze a single test file for mock usage with better error handling"""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        # Skip files with encoding or other issues
        return {
            'filepath': filepath,
            'mock_count': 0,
            'total_tests': 0,
            'mock_percentage': 0.0,
            'mock_lines': []
        }
    
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
    """테스트 파일 찾기 - claude-ops 프로젝트 테스트만"""
    test_files = []
    root_path = Path(root_dir)
    
    # claude-ops 프로젝트의 tests/ 디렉토리만 검색
    tests_dir = root_path / "tests"
    if tests_dir.exists():
        test_files.extend(tests_dir.glob("test_*.py"))
        test_files.extend(tests_dir.glob("*_test.py"))
    
    # 중복 제거 및 필터링 (claude-ops 프로젝트만)
    filtered_files = []
    for f in test_files:
        # Skip virtual environment and external dependencies
        if '.venv' not in str(f) and 'site-packages' not in str(f):
            filtered_files.append(f)
    
    return filtered_files

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
            # 허용되는 mock 패턴 체크
            allowed_patterns = [
                'subprocess.run',
                'subprocess.Popen', 
                'subprocess.call',
                'time.time',
                'time.sleep',
                'datetime.now',
                'requests.',
                'urllib.',
                'open',  # File I/O
                'os.system',
                'os.path.exists',
                'Path.exists',
                'Path.open',
                # Session state checks are I/O operations (tmux interactions)
                'get_screen_content',  # Tmux screen capture
                'get_state',  # External tmux state check
                'is_working',  # External process state
                'get_state_details',  # External process info
            ]
            
            # Mock 대상에서 실제 함수/메서드 이름 추출
            mock_target = usage.get('mock_target', '')
            
            # 전체 경로에서 실제 mock 대상만 확인
            # 예: 'claude_ctb.utils.session_state.subprocess.run' -> 'subprocess.run'
            is_allowed = any(pattern in mock_target for pattern in allowed_patterns)
            
            # Mock() 같은 직접 생성도 체크 - 이름에서 판단
            if not is_allowed and 'name' in usage:
                name = usage.get('name', '').lower()
                if any(ext in name for ext in ['mock', 'magicmock']):
                    # MagicMock이나 Mock 직접 사용은 기본적으로 허용 안함
                    is_allowed = False
            
            if is_allowed:
                category = 'external_service'  # 허용되는 외부 의존성
            else:
                category = 'internal_logic'  # 내부 로직 (비허용)
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
    
    print(f"\n📈 Overall Statistics:")
    print(f"   Total test methods: {report['total_tests']}")
    print(f"   Tests using mocks: {report['tests_with_mock']}")
    print(f"   Mock usage rate: {report['mock_percentage']:.1f}%")
    print(f"   Total mock usages: {report['total_mock_usages']}")
    
    print(f"\n📦 Mock Categories:")
    for category, count in report['categories'].items():
        emoji = "✅" if category != 'internal_logic' else "❌"
        print(f"   {emoji} {category}: {count}")
    
    # 제한 확인
    # Claude-ops는 tmux 상호작용이 많아 mock 사용이 필요함
    MAX_MOCK_PERCENTAGE = 35  # tmux 및 외부 프로세스 테스트를 위해 상향 조정
    
    if report['mock_percentage'] > MAX_MOCK_PERCENTAGE:
        print(f"\n❌ MOCK USAGE VIOLATION")
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
    
    print(f"\n✅ Mock Usage Check: PASSED")
    print(f"   Mock usage ({report['mock_percentage']:.1f}%) is within limit ({MAX_MOCK_PERCENTAGE}%)")
    
    # GitHub Actions 출력
    if report['mock_percentage'] > MAX_MOCK_PERCENTAGE:
        print(f"::error::Mock usage {report['mock_percentage']:.1f}% exceeds limit {MAX_MOCK_PERCENTAGE}%")
    elif report['mock_percentage'] > MAX_MOCK_PERCENTAGE * 0.8:
        print(f"::warning::Mock usage {report['mock_percentage']:.1f}% approaching limit {MAX_MOCK_PERCENTAGE}%")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())