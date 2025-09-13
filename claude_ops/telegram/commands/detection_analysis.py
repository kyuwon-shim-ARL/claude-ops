"""
Detection Analysis Telegram Commands

보수적 working detection의 성과를 분석하고 개선 방향을 제시하는 명령어들
"""

from telegram import Update
from telegram.ext import ContextTypes
import logging

from ...monitoring.missed_case_analyzer import missed_case_analyzer
from ...utils.conservative_detector import conservative_detector

logger = logging.getLogger(__name__)


async def detection_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /detection_status - 현재 탐지 성능 상태 확인
    """
    try:
        # 현재 분석 실행
        analysis = missed_case_analyzer.analyze_current_state()
        summary = analysis["summary"]
        
        if summary["total"] == 0:
            status_emoji = "🎯"
            status_text = "완벽"
            message = "보수적 접근이 완벽하게 작동 중입니다!"
        elif summary["total"] <= 5:
            status_emoji = "✅"
            status_text = "우수"
            message = f"최근 {summary['total']}개 케이스만 놓침 - 매우 좋은 성능"
        elif summary["total"] <= 15:
            status_emoji = "⚠️"
            status_text = "양호"
            message = f"{summary['total']}개 케이스 놓침 - 개선 여지 있음"
        else:
            status_emoji = "🔍"
            status_text = "개선 필요"
            message = f"{summary['total']}개 케이스 놓침 - 패턴 분석 필요"
        
        response = f"""
{status_emoji} **Working Detection 상태: {status_text}**

📊 **요약**
- 놓친 케이스: {summary['total']}개
- 분석 기간: 최근 100개 케이스
- {message}

🎯 **주요 제안**
"""
        
        for suggestion in analysis["suggestions"][:3]:
            response += f"• {suggestion}\n"
        
        if summary.get("patterns"):
            response += f"\n🔍 **자주 놓친 패턴 TOP 3**\n"
            patterns = list(summary["patterns"].items())[:3]
            for pattern, count in patterns:
                percentage = (count / summary["total"]) * 100
                response += f"• `{pattern}`: {count}회 ({percentage:.1f}%)\n"
        
        await update.message.reply_text(response, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in detection_status: {e}")
        await update.message.reply_text(f"❌ 상태 확인 중 오류: {e}")


async def detection_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /detection_report - 상세 분석 보고서 생성
    """
    try:
        # 상세 보고서 생성
        report = missed_case_analyzer.export_report()
        
        # 길이 제한 (텔레그램 메시지 한계)
        if len(report) > 4000:
            # 앞부분만 보내고 나머지는 요약
            truncated = report[:3500]
            truncated += f"\n\n... (총 {len(report)}자, 요약됨)\n\n"
            truncated += "📝 전체 보고서는 /detection_export 명령으로 확인 가능"
            report = truncated
        
        await update.message.reply_text(f"```\n{report}\n```", parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in detection_report: {e}")
        await update.message.reply_text(f"❌ 보고서 생성 중 오류: {e}")


async def detection_trends(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /detection_trends - 최근 트렌드 분석
    """
    try:
        # 일수 파라미터 (기본 7일)
        days = 7
        if context.args and context.args[0].isdigit():
            days = int(context.args[0])
            days = min(30, max(1, days))  # 1-30일 제한
        
        trend = missed_case_analyzer.get_trend_analysis(days)
        
        if "message" in trend:
            await update.message.reply_text(f"📊 {trend['message']}")
            return
        
        missed = trend["missed_cases"]
        trend_emoji = "📈" if missed["trend"] == "increasing" else "📉"
        
        response = f"""
📊 **{days}일 트렌드 분석**

{trend_emoji} **놓친 케이스 변화**
- 시작: {missed['first']}개
- 현재: {missed['last']}개  
- 평균: {missed['average']:.1f}개
- 추세: {missed['trend']}

📈 **분석 횟수**: {trend['analyses_count']}회
"""
        
        if "top_missed_pattern" in trend:
            top = trend["top_missed_pattern"]
            response += f"""
🔍 **가장 많이 놓친 패턴**
- `{top['pattern']}`: {top['total_occurrences']}회
"""
        
        # 개선 제안
        if missed["trend"] == "increasing":
            response += f"\n⚠️ **제안**: 놓친 케이스가 증가 중입니다. /detection_improve 검토 권장"
        else:
            response += f"\n✅ **상태**: 개선되고 있는 추세입니다."
        
        await update.message.reply_text(response, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in detection_trends: {e}")
        await update.message.reply_text(f"❌ 트렌드 분석 중 오류: {e}")


async def detection_improve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /detection_improve - 개선 계획 생성
    """
    try:
        plan = missed_case_analyzer.generate_improvement_plan()
        
        response = f"""
🎯 **Detection 개선 계획**
생성일: {plan['timestamp'][:19].replace('T', ' ')}

📊 **현재 상태**: {plan['current_status'].replace('_', ' ').title()}

🔧 **개선 권장사항**:
"""
        
        for i, rec in enumerate(plan["recommendations"], 1):
            priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(rec["priority"], "⚪")
            
            response += f"""
**{i}. {rec['type'].replace('_', ' ').title()}** {priority_emoji}
- 우선순위: {rec['priority']}
- 근거: {rec['rationale']}
- 구현: {rec['implementation']}
- 리스크: {rec['risk']}
"""
        
        # 다음 단계 안내
        response += f"""
📋 **다음 단계**:
1. 위 권장사항 검토
2. 필요시 설정 변경
3. 1주일 후 /detection_trends 재확인
"""
        
        await update.message.reply_text(response, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in detection_improve: {e}")
        await update.message.reply_text(f"❌ 개선 계획 생성 중 오류: {e}")


# 명령어 핸들러 목록
DETECTION_COMMANDS = {
    'detection_status': detection_status,
    'detection_report': detection_report, 
    'detection_trends': detection_trends,
    'detection_improve': detection_improve,
}