#!/usr/bin/env python3
"""
Comprehensive Test-AI-Driven Development (TADD) Validator
포괄적 테스트 품질 검증 도구

이 스크립트는 다음을 검증합니다:
1. 테스트 커버리지 (최소 80%)
2. E2E 테스트 존재 (최소 1개)
3. 실제 데이터 사용 검증
4. 성능 벤치마크 측정
5. AI 작성 테스트 품질
"""

import os
import sys
import subprocess
import json
import glob
from pathlib import Path
from typing import Dict, List, Tuple, Optional

class TADDValidator:
    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.results = {}
        
    def check_coverage(self) -> Dict:
        """테스트 커버리지 검사"""
        print("📊 Checking test coverage...")
        
        coverage_result = {
            "score": 0,
            "status": "FAIL",
            "details": "No coverage data found"
        }
        
        try:
            # pytest-cov 시도
            result = subprocess.run(
                ["python", "-m", "pytest", "--cov=.", "--cov-report=term-missing", "--tb=no"],
                capture_output=True, text=True, cwd=self.project_root
            )
            
            if result.returncode == 0:
                # 커버리지 퍼센트 추출
                for line in result.stdout.split('\n'):
                    if 'TOTAL' in line and '%' in line:
                        try:
                            coverage_percent = int(line.split()[-1].replace('%', ''))
                            coverage_result = {
                                "score": coverage_percent,
                                "status": "PASS" if coverage_percent >= 80 else "FAIL",
                                "details": f"Coverage: {coverage_percent}%"
                            }
                        except (ValueError, IndexError):
                            pass
            
        except FileNotFoundError:
            coverage_result["details"] = "pytest not installed"
        
        return coverage_result
    
    def check_e2e_tests(self) -> Dict:
        """E2E 테스트 존재 확인"""
        print("🌐 Checking E2E tests...")
        
        # E2E 테스트 파일 패턴
        e2e_patterns = [
            "**/test*e2e*.py",
            "**/e2e*.py", 
            "**/integration*.py",
            "**/*playwright*.py",
            "**/*selenium*.py"
        ]
        
        e2e_files = []
        for pattern in e2e_patterns:
            e2e_files.extend(glob.glob(str(self.project_root / pattern), recursive=True))
        
        return {
            "count": len(e2e_files),
            "status": "PASS" if len(e2e_files) >= 1 else "FAIL",
            "details": f"Found {len(e2e_files)} E2E test files: {[os.path.basename(f) for f in e2e_files[:3]]}"
        }
    
    def check_real_data_usage(self) -> Dict:
        """실제 데이터 사용 검증"""
        print("💾 Checking real data usage...")
        
        mock_indicators = ["Mock", "patch", "fake", "stub", "dummy"]
        real_data_indicators = ["fixtures", "database", "api", "file", "csv", "json"]
        
        mock_count = 0
        real_data_count = 0
        
        test_files = glob.glob(str(self.project_root / "**/test*.py"), recursive=True)
        
        for test_file in test_files:
            try:
                with open(test_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                for indicator in mock_indicators:
                    mock_count += content.count(indicator)
                    
                for indicator in real_data_indicators:
                    real_data_count += content.count(indicator)
                    
            except Exception:
                continue
        
        real_data_ratio = (real_data_count / (real_data_count + mock_count)) * 100 if (real_data_count + mock_count) > 0 else 0
        
        return {
            "real_data_ratio": round(real_data_ratio, 1),
            "status": "PASS" if real_data_ratio >= 60 else "FAIL",
            "details": f"Real data usage: {real_data_ratio:.1f}% (Mock: {mock_count}, Real: {real_data_count})"
        }
    
    def check_performance_tests(self) -> Dict:
        """성능 테스트 존재 확인"""
        print("⚡ Checking performance tests...")
        
        perf_patterns = [
            "**/test*perf*.py",
            "**/test*benchmark*.py",
            "**/perf*.py",
            "**/benchmark*.py"
        ]
        
        perf_files = []
        for pattern in perf_patterns:
            perf_files.extend(glob.glob(str(self.project_root / pattern), recursive=True))
        
        # 성능 측정 키워드 검색
        perf_keywords = ["time", "benchmark", "performance", "speed", "latency"]
        perf_test_count = 0
        
        test_files = glob.glob(str(self.project_root / "**/test*.py"), recursive=True)
        for test_file in test_files:
            try:
                with open(test_file, 'r', encoding='utf-8') as f:
                    content = f.read().lower()
                    if any(keyword in content for keyword in perf_keywords):
                        perf_test_count += 1
            except Exception:
                continue
        
        total_perf_indicators = len(perf_files) + perf_test_count
        
        return {
            "count": total_perf_indicators,
            "status": "PASS" if total_perf_indicators >= 1 else "WARN",
            "details": f"Performance indicators: {total_perf_indicators} (files: {len(perf_files)}, keywords: {perf_test_count})"
        }
    
    def check_ai_test_quality(self) -> Dict:
        """AI 작성 테스트 품질 확인"""
        print("🤖 Checking AI test quality...")
        
        # AI 작성 테스트 지표
        quality_indicators = {
            "descriptive_names": 0,
            "assertions": 0,
            "edge_cases": 0,
            "documentation": 0
        }
        
        test_files = glob.glob(str(self.project_root / "**/test*.py"), recursive=True)
        
        for test_file in test_files:
            try:
                with open(test_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # 설명적 테스트 이름
                if "should" in content or "when" in content or "given" in content:
                    quality_indicators["descriptive_names"] += 1
                
                # 적절한 assertion 수
                assert_count = content.count("assert")
                if assert_count >= 3:  # 최소 3개 assertion
                    quality_indicators["assertions"] += 1
                
                # 엣지 케이스 테스트
                edge_keywords = ["empty", "null", "None", "zero", "negative", "maximum"]
                if any(keyword in content for keyword in edge_keywords):
                    quality_indicators["edge_cases"] += 1
                
                # 테스트 문서화
                if '"""' in content or "'''" in content:
                    quality_indicators["documentation"] += 1
                    
            except Exception:
                continue
        
        total_quality_score = sum(quality_indicators.values())
        max_possible_score = len(test_files) * 4  # 4 indicators per file
        quality_percentage = (total_quality_score / max_possible_score * 100) if max_possible_score > 0 else 0
        
        return {
            "score": round(quality_percentage, 1),
            "status": "PASS" if quality_percentage >= 70 else "FAIL",
            "details": f"AI test quality: {quality_percentage:.1f}% ({total_quality_score}/{max_possible_score} points)",
            "breakdown": quality_indicators
        }
    
    def run_comprehensive_validation(self) -> Dict:
        """전체 검증 실행"""
        print("🎯 Running comprehensive TADD validation...")
        print("=" * 50)
        
        self.results = {
            "coverage": self.check_coverage(),
            "e2e_tests": self.check_e2e_tests(),
            "real_data": self.check_real_data_usage(),
            "performance": self.check_performance_tests(),
            "ai_quality": self.check_ai_test_quality()
        }
        
        # 전체 점수 계산
        total_score = 0
        max_score = 0
        
        for category, result in self.results.items():
            if "score" in result:
                total_score += result["score"]
                max_score += 100
            elif result["status"] == "PASS":
                total_score += 100
                max_score += 100
            elif result["status"] == "WARN":
                total_score += 50
                max_score += 100
            else:
                max_score += 100
        
        overall_score = (total_score / max_score * 100) if max_score > 0 else 0
        
        self.results["overall"] = {
            "score": round(overall_score, 1),
            "status": "PASS" if overall_score >= 80 else "FAIL",
            "details": f"Overall TADD compliance: {overall_score:.1f}%"
        }
        
        return self.results
    
    def print_report(self):
        """검증 결과 출력"""
        print("\n" + "=" * 50)
        print("📊 COMPREHENSIVE TADD VALIDATION REPORT")
        print("=" * 50)
        
        for category, result in self.results.items():
            if category == "overall":
                continue
                
            status_emoji = "✅" if result["status"] == "PASS" else "⚠️" if result["status"] == "WARN" else "❌"
            print(f"{status_emoji} {category.upper()}: {result['details']}")
        
        print("\n" + "-" * 50)
        overall = self.results.get("overall", {})
        status_emoji = "✅" if overall.get("status") == "PASS" else "❌"
        print(f"{status_emoji} OVERALL: {overall.get('details', 'No overall score')}")
        
        if overall.get("status") == "FAIL":
            print("\n💡 Recommendations:")
            if self.results["coverage"]["status"] == "FAIL":
                print("   - Increase test coverage to 80%+")
            if self.results["e2e_tests"]["status"] == "FAIL":
                print("   - Add at least 1 E2E test")
            if self.results["real_data"]["status"] == "FAIL":
                print("   - Use more real data, reduce mocks")
            if self.results["ai_quality"]["status"] == "FAIL":
                print("   - Improve AI test quality (descriptive names, assertions)")


def main():
    if len(sys.argv) > 1:
        project_root = sys.argv[1]
    else:
        project_root = "."
    
    validator = TADDValidator(project_root)
    results = validator.run_comprehensive_validation()
    validator.print_report()
    
    # JSON 출력 (다른 스크립트에서 파싱 가능)
    with open("tadd_validation_report.json", "w") as f:
        json.dump(results, f, indent=2)
    
    # 전체 검증 실패시 exit code 1
    if results["overall"]["status"] == "FAIL":
        sys.exit(1)
    
    sys.exit(0)


if __name__ == "__main__":
    main()