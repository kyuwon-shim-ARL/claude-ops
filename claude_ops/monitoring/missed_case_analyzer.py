"""
Missed Case Analyzer

보수적 접근으로 놓친 케이스들을 분석하고 개선 방향을 제시하는 도구
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import asdict
from pathlib import Path

from ..utils.conservative_detector import conservative_detector

logger = logging.getLogger(__name__)


class MissedCaseAnalyzer:
    """놓친 케이스 분석기"""
    
    def __init__(self, data_path: str = "/tmp/missed_cases_analysis.json"):
        self.data_path = Path(data_path)
        self.analysis_history: List[Dict[str, Any]] = []
        self.load_history()
    
    def analyze_current_state(self) -> Dict[str, Any]:
        """현재 놓친 케이스들 분석"""
        summary = conservative_detector.get_missed_cases_summary()
        suggestions = conservative_detector.suggest_improvements()
        
        analysis = {
            "timestamp": datetime.now().isoformat(),
            "summary": summary,
            "suggestions": suggestions,
            "analysis": self._deep_analysis(summary)
        }
        
        # 히스토리에 추가
        self.analysis_history.append(analysis)
        self.save_history()
        
        return analysis
    
    def _deep_analysis(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        """심층 분석"""
        if summary["total"] == 0:
            return {
                "status": "excellent",
                "message": "No missed cases - conservative approach working perfectly",
                "action": "continue"
            }
        
        patterns = summary.get("patterns", {})
        total = summary["total"]
        
        # 상위 패턴 분석
        top_pattern = max(patterns.items(), key=lambda x: x[1]) if patterns else None
        
        if not top_pattern:
            return {
                "status": "unknown",
                "message": "Missed cases without clear patterns",
                "action": "investigate"
            }
        
        pattern, count = top_pattern
        percentage = (count / total) * 100
        
        if percentage >= 50:
            return {
                "status": "clear_pattern",
                "message": f"'{pattern}' appears in {percentage:.1f}% of missed cases",
                "action": f"consider_adding",
                "candidate_pattern": pattern,
                "confidence": "high" if percentage >= 70 else "medium"
            }
        elif percentage >= 30:
            return {
                "status": "emerging_pattern", 
                "message": f"'{pattern}' is emerging as important ({percentage:.1f}%)",
                "action": "monitor",
                "candidate_pattern": pattern,
                "confidence": "medium"
            }
        else:
            return {
                "status": "diverse_patterns",
                "message": "Missed cases are diverse - conservative approach appropriate",
                "action": "continue"
            }
    
    def generate_improvement_plan(self) -> Dict[str, Any]:
        """개선 계획 생성"""
        current = self.analyze_current_state()
        analysis = current["analysis"]
        
        plan = {
            "timestamp": datetime.now().isoformat(),
            "current_status": analysis["status"],
            "recommendations": []
        }
        
        if analysis["status"] == "clear_pattern":
            pattern = analysis["candidate_pattern"]
            confidence = analysis["confidence"]
            
            plan["recommendations"].append({
                "type": "add_pattern",
                "pattern": pattern,
                "priority": "high" if confidence == "high" else "medium",
                "rationale": f"Appears in majority of missed cases ({analysis['message']})",
                "implementation": f"Move '{pattern}' to high_confidence_patterns",
                "risk": "low" if "Running" in pattern or "Building" in pattern else "medium"
            })
        
        elif analysis["status"] == "emerging_pattern":
            pattern = analysis["candidate_pattern"]
            
            plan["recommendations"].append({
                "type": "monitor_pattern", 
                "pattern": pattern,
                "priority": "low",
                "rationale": f"Emerging pattern worth monitoring ({analysis['message']})",
                "implementation": f"Continue tracking '{pattern}' for 1 week",
                "risk": "none"
            })
        
        else:
            plan["recommendations"].append({
                "type": "maintain_status",
                "priority": "low", 
                "rationale": analysis["message"],
                "implementation": "Continue with current conservative approach",
                "risk": "none"
            })
        
        return plan
    
    def get_trend_analysis(self, days: int = 7) -> Dict[str, Any]:
        """트렌드 분석"""
        cutoff = datetime.now() - timedelta(days=days)
        
        recent_analyses = [
            a for a in self.analysis_history 
            if datetime.fromisoformat(a["timestamp"]) > cutoff
        ]
        
        if len(recent_analyses) < 2:
            return {"message": "Not enough data for trend analysis"}
        
        # 놓친 케이스 수 트렌드
        missed_counts = [a["summary"]["total"] for a in recent_analyses]
        
        trend = {
            "period_days": days,
            "analyses_count": len(recent_analyses),
            "missed_cases": {
                "first": missed_counts[0],
                "last": missed_counts[-1], 
                "average": sum(missed_counts) / len(missed_counts),
                "trend": "increasing" if missed_counts[-1] > missed_counts[0] else "decreasing"
            }
        }
        
        # 패턴 트렌드
        all_patterns = {}
        for analysis in recent_analyses:
            for pattern, count in analysis["summary"].get("patterns", {}).items():
                all_patterns[pattern] = all_patterns.get(pattern, 0) + count
        
        if all_patterns:
            top_pattern = max(all_patterns.items(), key=lambda x: x[1])
            trend["top_missed_pattern"] = {
                "pattern": top_pattern[0],
                "total_occurrences": top_pattern[1]
            }
        
        return trend
    
    def save_history(self):
        """분석 히스토리 저장"""
        try:
            with open(self.data_path, 'w') as f:
                json.dump(self.analysis_history, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save analysis history: {e}")
    
    def load_history(self):
        """분석 히스토리 로드"""
        try:
            if self.data_path.exists():
                with open(self.data_path, 'r') as f:
                    self.analysis_history = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load analysis history: {e}")
            self.analysis_history = []
    
    def export_report(self) -> str:
        """분석 보고서 생성"""
        current = self.analyze_current_state()
        plan = self.generate_improvement_plan()
        trend = self.get_trend_analysis()
        
        report = f"""
# 보수적 Working Detection 분석 보고서
생성일: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 📊 현재 상태
- 총 놓친 케이스: {current['summary']['total']}개
- 상태: {current['analysis']['status']}
- 메시지: {current['analysis']['message']}

## 🎯 개선 제안
"""
        
        for rec in plan["recommendations"]:
            report += f"""
### {rec['type'].replace('_', ' ').title()}
- 우선순위: {rec['priority']}
- 근거: {rec['rationale']}
- 구현: {rec['implementation']}
- 리스크: {rec['risk']}
"""
        
        if current['summary']['patterns']:
            report += f"""
## 📈 놓친 패턴 분석
"""
            for pattern, count in list(current['summary']['patterns'].items())[:5]:
                percentage = (count / current['summary']['total']) * 100
                report += f"- `{pattern}`: {count}회 ({percentage:.1f}%)\n"
        
        if "missed_cases" in trend:
            report += f"""
## 📊 7일 트렌드
- 놓친 케이스 변화: {trend['missed_cases']['first']} → {trend['missed_cases']['last']} ({trend['missed_cases']['trend']})
- 평균: {trend['missed_cases']['average']:.1f}개/일
"""
        
        return report


# 글로벌 인스턴스
missed_case_analyzer = MissedCaseAnalyzer()