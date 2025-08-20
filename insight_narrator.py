from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import json
import os
import statistics
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage, SystemMessage
from langchain_community.callbacks.manager import get_openai_callback
from models import *
from database import Database


class InsightNarrator:
    def __init__(self, db: Database, openai_api_key: str = None):
        self.db = db
        
        # Primary LLM (OpenAI)
        try:
            self.llm = ChatOpenAI(
                model_name="gpt-4.1",
                temperature=0.3,
                openai_api_key=openai_api_key or os.getenv("OPENAI_API_KEY")
            )
            print("✅ OpenAI initialized")
        except Exception as e:
            print(f"❌ Failed to initialize OpenAI: {e}")
            self.llm = None
        
        # Fallback LLM (Gemini)
        try:
            gemini_key = os.getenv("GEMINI_API_KEY")
            if gemini_key:
                self.gemini_llm = ChatGoogleGenerativeAI(
                    model="gemini-2.5-flash",
                    temperature=0.3,
                    google_api_key=gemini_key
                )
                print("✅ Gemini initialized successfully")
            else:
                print("⚠️ No Gemini API key found")
                self.gemini_llm = None
        except Exception as e:
            print(f"❌ Failed to initialize Gemini: {e}")
            self.gemini_llm = None
        
        self.system_prompts = {
            "daily": self._get_daily_system_prompt(),
            "weekly": self._get_weekly_system_prompt(),
            "monthly": self._get_monthly_system_prompt()
        }
    
    def generate_insight_narrative(self, dora_metrics: DORAMetrics, 
                                 churn_alerts: List[ChurnAlert],
                                 risk_assessment: Dict[str, Any]) -> InsightNarrative:
        
        period = dora_metrics.period.value
        system_prompt = self.system_prompts.get(period, self._get_weekly_system_prompt())
        
        context_data = {
            "dora_metrics": dora_metrics.dict(),
            "churn_alerts": [alert.dict() for alert in churn_alerts],
            "risk_assessment": risk_assessment,
            "period": period,
            "date_range": f"{dora_metrics.start_date.date()} to {dora_metrics.end_date.date()}"
        }
        
        human_prompt = self._build_human_prompt(context_data)
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt)
        ]
        
        # Try OpenAI first, then Gemini as fallback
        response = None
        prompt_tokens = 0
        completion_tokens = 0
        model_used = "fallback"
        
        try:
            if self.llm:
                print("🔄 Trying OpenAI...")
                with get_openai_callback() as cb:
                    response = self.llm.invoke(messages)
                    prompt_tokens = cb.prompt_tokens
                    completion_tokens = cb.completion_tokens
                    model_used = "gpt-4.1"
                    print("✅ OpenAI response generated successfully")
        except Exception as e:
            print(f"❌ OpenAI failed: {e}")
            try:
                if self.gemini_llm:
                    print("🔄 Trying Gemini fallback...")
                    response = self.gemini_llm.invoke(messages)
                    model_used = "gemini-2.5-flash"
                    print("✅ Gemini response generated successfully")
                else:
                    print("❌ Gemini not available")
            except Exception as e2:
                print(f"❌ Gemini also failed: {e2}")
                response = None
        
        if response:
            parsed_response = self._parse_llm_response(response.content)
        else:
            # Use default response if both fail
            parsed_response = {
                "summary": "Unable to generate AI insights due to API limitations. Using default analysis.",
                "key_insights": [
                    "Team activity detected in the specified period",
                    "Metrics calculated successfully",
                    "Consider reviewing team productivity patterns"
                ],
                "recommendations": [
                    "Check API quota and retry for detailed insights",
                    "Review team performance metrics manually"
                ]
            }
        
        narrative = InsightNarrative(
            period=dora_metrics.period,
            start_date=dora_metrics.start_date,
            end_date=dora_metrics.end_date,
            repository=dora_metrics.repository,
            author=dora_metrics.author,
            summary=parsed_response.get("summary", ""),
            key_insights=parsed_response.get("key_insights", []),
            recommendations=parsed_response.get("recommendations", []),
            alerts=churn_alerts,
            dora_metrics=dora_metrics,
            llm_model=model_used,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens
        )
        
        return narrative
    
    def _get_daily_system_prompt(self) -> str:
        return """You are an expert engineering productivity analyst. Generate daily insights for engineering teams based on DORA metrics and code churn data.

Your role is to:
1. Analyze development velocity and quality metrics
2. Identify productivity patterns and bottlenecks
3. Provide actionable recommendations for improvement
4. Highlight any concerning trends or anomalies

Format your response as JSON with these fields:
- summary: A concise 2-3 sentence overview
- key_insights: Array of 3-5 specific insights
- recommendations: Array of 2-4 actionable recommendations

Focus on:
- Daily development velocity
- Code quality indicators
- Team collaboration patterns
- Immediate actionable items

Keep the tone professional but accessible. Use specific metrics when relevant."""
    
    def _get_weekly_system_prompt(self) -> str:
        return """You are an expert engineering productivity analyst. Generate weekly insights for engineering teams based on DORA metrics and code churn analysis.

Your role is to:
1. Analyze weekly development patterns and trends
2. Evaluate team performance against DORA four key metrics
3. Identify code churn risks and quality concerns
4. Provide strategic recommendations for the upcoming week

Format your response as JSON with these fields:
- summary: A comprehensive 3-4 sentence overview
- key_insights: Array of 4-6 specific insights with metrics
- recommendations: Array of 3-5 strategic recommendations

Focus on:
- DORA metrics trends (lead time, deployment frequency, change failure rate, MTTR)
- Code churn patterns and risk indicators
- Team productivity and collaboration
- Process improvements and optimization opportunities

Use data-driven insights and provide specific metrics. Keep recommendations actionable and prioritized."""
    
    def _get_monthly_system_prompt(self) -> str:
        return """You are an expert engineering productivity analyst. Generate monthly insights for engineering leadership based on comprehensive DORA metrics and team performance data.

Your role is to:
1. Analyze monthly engineering productivity trends
2. Evaluate team performance against industry benchmarks
3. Identify systemic issues and improvement opportunities
4. Provide strategic recommendations for leadership

Format your response as JSON with these fields:
- summary: A strategic 4-5 sentence overview for leadership
- key_insights: Array of 5-7 detailed insights with context
- recommendations: Array of 4-6 strategic recommendations

Focus on:
- Long-term DORA metrics trends and benchmarking
- Team capacity and scaling considerations
- Process maturity and optimization
- Risk management and technical debt
- Strategic planning insights

Provide executive-level insights suitable for engineering leadership decision-making."""
    
    def _build_human_prompt(self, context_data: Dict[str, Any]) -> str:
        metrics = context_data["dora_metrics"]
        alerts = context_data["churn_alerts"]
        risk = context_data["risk_assessment"]
        
        prompt = f"""Analyze the following engineering productivity data for {context_data['date_range']} ({context_data['period']} report):

DORA METRICS:
- Lead Time: {metrics['lead_time_hours']:.1f} hours
- Deployment Frequency: {metrics['deployment_frequency']:.2f} deploys/day
- Change Failure Rate: {metrics['change_failure_rate']:.2%}
- Mean Time to Recovery: {metrics['mean_time_to_recovery_hours']:.1f} hours

DEVELOPMENT ACTIVITY:
- Commits: {metrics['commits_count']}
- Pull Requests: {metrics['pull_requests_count']} (merged: {metrics['merged_prs_count']})
- Code Changes: +{metrics['total_additions']} -{metrics['total_deletions']} lines
- Files Changed: {metrics['total_files_changed']}
- Churn Score: {metrics['churn_score']:.1f}

QUALITY METRICS:
- Review Time: {metrics['review_time_hours']:.1f} hours
- Cycle Time: {metrics['cycle_time_hours']:.1f} hours
- CI Failures: {metrics['ci_failures_count']}

RISK ASSESSMENT:
- Overall Risk Level: {risk['overall_risk_level']}
- Active Alerts: {len(alerts)}
- Risk Factors: {', '.join(risk['risk_factors']) if risk['risk_factors'] else 'None'}

CHURN ALERTS:
"""
        
        for alert in alerts:
            prompt += f"- {alert['author']}: {alert['churn_score']:.1f}x above average ({alert['risk_level']} risk)\n"
        
        prompt += "\nGenerate insights that help engineering teams improve their productivity and code quality."
        
        return prompt
    
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        try:
            # First, try direct JSON parsing
            parsed = json.loads(response)
            
            # Convert complex objects to strings if needed
            if "key_insights" in parsed and isinstance(parsed["key_insights"], list):
                insights = []
                for insight in parsed["key_insights"]:
                    if isinstance(insight, dict):
                        # Extract meaningful text from dict objects
                        text = insight.get("insight", "") or insight.get("description", "") or insight.get("metric", "") or str(insight)
                        insights.append(text)
                    else:
                        insights.append(str(insight))
                parsed["key_insights"] = insights
            
            if "recommendations" in parsed and isinstance(parsed["recommendations"], list):
                recommendations = []
                for rec in parsed["recommendations"]:
                    if isinstance(rec, dict):
                        # Extract meaningful text from dict objects
                        text = rec.get("recommendation", "") or rec.get("action", "") or rec.get("description", "") or str(rec)
                        recommendations.append(text)
                    else:
                        recommendations.append(str(rec))
                parsed["recommendations"] = recommendations
            
            return parsed
            
        except json.JSONDecodeError:
            try:
                # Try to extract JSON from markdown code blocks
                import re
                json_match = re.search(r'```(?:json)?\s*(\{.*\})\s*```', response, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group(1))
                    # Apply the same conversion logic
                    return self._parse_llm_response(json_match.group(1))
                
                # Try to find JSON-like content in the response
                json_match = re.search(r'\{[^{}]*"summary"[^{}]*\}', response, re.DOTALL)
                if json_match:
                    return self._parse_llm_response(json_match.group(0))
                    
            except (json.JSONDecodeError, AttributeError):
                pass
            
            # If all parsing fails, try to extract structured information
            print(f"⚠️ Failed to parse JSON, attempting text extraction from: {response[:200]}...")
            
            # Extract summary, insights, and recommendations using text processing
            summary = self._extract_summary_from_text(response)
            insights = self._extract_insights_from_text(response)
            recommendations = self._extract_recommendations_from_text(response)
            
            return {
                "summary": summary,
                "key_insights": insights,
                "recommendations": recommendations
            }
    
    def _extract_summary_from_text(self, text: str) -> str:
        """Extract summary from free-form text"""
        lines = text.split('\n')
        for line in lines:
            if line.strip() and not line.startswith('-') and not line.startswith('*'):
                return line.strip()[:200]  # First substantial line, limited length
        return "AI-generated analysis of team productivity metrics and development patterns."
    
    def _extract_insights_from_text(self, text: str) -> List[str]:
        """Extract insights from free-form text"""
        insights = []
        lines = text.split('\n')
        
        # Look for bullet points or numbered lists
        for line in lines:
            line = line.strip()
            if line.startswith(('- ', '* ', '• ')) or (line and line[0].isdigit() and '. ' in line):
                insight = line.lstrip('- *•0123456789. ').strip()
                if len(insight) > 10:  # Filter out short lines
                    insights.append(insight)
        
        # If no structured insights found, create generic ones
        if not insights:
            insights = [
                "Development activity analyzed across the specified time period",
                "DORA metrics calculated and benchmarked against industry standards",
                "Code quality and team productivity patterns identified"
            ]
        
        return insights[:6]  # Limit to 6 insights
    
    def _extract_recommendations_from_text(self, text: str) -> List[str]:
        """Extract recommendations from free-form text"""
        recommendations = []
        
        # Look for recommendation keywords
        text_lower = text.lower()
        if 'recommend' in text_lower or 'suggest' in text_lower or 'should' in text_lower:
            lines = text.split('\n')
            for line in lines:
                line_lower = line.lower()
                if any(word in line_lower for word in ['recommend', 'suggest', 'should', 'consider']):
                    rec = line.strip().lstrip('- *•0123456789. ')
                    if len(rec) > 15:  # Filter out short lines
                        recommendations.append(rec)
        
        # If no recommendations found, provide generic ones
        if not recommendations:
            recommendations = [
                "Continue monitoring development velocity and quality metrics",
                "Review team capacity and workload distribution regularly",
                "Consider implementing automated quality checks where beneficial"
            ]
        
        return recommendations[:5]  # Limit to 5 recommendations
    
    def generate_comparative_analysis(self, current_metrics: DORAMetrics, 
                                    historical_metrics: List[DORAMetrics]) -> Dict[str, Any]:
        if not historical_metrics:
            return {"analysis": "No historical data available for comparison"}
        
        comparison_data = {
            "current": current_metrics.dict(),
            "historical": [m.dict() for m in historical_metrics[-4:]]
        }
        
        system_prompt = """You are an expert engineering productivity analyst. Compare current metrics with historical data to identify trends and patterns.

Analyze the progression of DORA metrics over time and provide insights on:
- Performance trends (improving, declining, stable)
- Seasonal or cyclical patterns
- Significant changes or anomalies
- Comparative performance assessment

Format your response as JSON with:
- trend_analysis: Overall trend assessment
- key_changes: Significant changes from previous periods
- performance_indicators: Current vs historical performance
- recommendations: Actions based on trends"""
        
        human_prompt = f"Compare current metrics with historical data:\n\n{json.dumps(comparison_data, indent=2)}"
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt)
        ]
        
        response = self.llm(messages)
        return self._parse_llm_response(response.content)
    
    def generate_team_summary(self, team_metrics: List[DORAMetrics]) -> Dict[str, Any]:
        if not team_metrics:
            return {"summary": "No team metrics available"}
        
        team_data = {
            "team_metrics": [m.dict() for m in team_metrics],
            "team_size": len(team_metrics),
            "total_commits": sum(m.commits_count for m in team_metrics),
            "total_prs": sum(m.pull_requests_count for m in team_metrics),
            "avg_lead_time": sum(m.lead_time_hours for m in team_metrics) / len(team_metrics),
            "avg_cycle_time": sum(m.cycle_time_hours for m in team_metrics) / len(team_metrics)
        }
        
        system_prompt = """You are an expert engineering productivity analyst. Generate team-level insights based on individual contributor metrics.

Analyze the team's collective performance and provide:
- Team velocity and throughput analysis
- Individual contributor patterns and balance
- Collaboration effectiveness
- Team capacity and workload distribution
- Areas for team improvement

Format your response as JSON with:
- team_summary: Overall team performance assessment
- individual_highlights: Notable individual contributions
- collaboration_insights: Team collaboration patterns
- capacity_analysis: Workload and capacity insights
- team_recommendations: Team-level improvement suggestions"""
        
        human_prompt = f"Analyze team performance data:\n\n{json.dumps(team_data, indent=2)}"
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt)
        ]
        
        response = self.llm(messages)
        return self._parse_llm_response(response.content)
    
    def generate_executive_summary(self, narrative: InsightNarrative) -> str:
        system_prompt = """You are an executive communication specialist. Transform technical engineering insights into executive-level summary suitable for leadership.

Focus on:
- Business impact and implications
- Strategic recommendations
- Risk management priorities
- Resource allocation insights
- ROI and efficiency metrics

Keep the summary concise (3-4 paragraphs) and business-focused."""
        
        human_prompt = f"""Transform this technical analysis into an executive summary:

SUMMARY: {narrative.summary}

KEY INSIGHTS:
{chr(10).join(f'- {insight}' for insight in narrative.key_insights)}

RECOMMENDATIONS:
{chr(10).join(f'- {rec}' for rec in narrative.recommendations)}

METRICS OVERVIEW:
- Lead Time: {narrative.dora_metrics.lead_time_hours:.1f} hours
- Deployment Frequency: {narrative.dora_metrics.deployment_frequency:.2f}/day
- Change Failure Rate: {narrative.dora_metrics.change_failure_rate:.2%}
- Team Velocity: {narrative.dora_metrics.commits_count} commits, {narrative.dora_metrics.merged_prs_count} PRs merged
- Code Quality: {len(narrative.alerts)} alerts, {narrative.dora_metrics.churn_score:.1f} churn score"""
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt)
        ]
        
        response = self.llm(messages)
        return response.content
    
    def save_narrative(self, narrative: InsightNarrative) -> int:
        with self.db.get_session() as session:
            narrative_data = {
                "period": narrative.period.value,
                "start_date": narrative.start_date,
                "end_date": narrative.end_date,
                "repository_id": None,
                "author_id": None,
                "summary": narrative.summary,
                "key_insights": narrative.key_insights,
                "recommendations": narrative.recommendations,
                "alerts": [alert.dict() for alert in narrative.alerts],
                "llm_model": narrative.llm_model,
                "prompt_tokens": narrative.prompt_tokens,
                "completion_tokens": narrative.completion_tokens
            }
            
            saved_narrative = self.db.save_insight_narrative(session, narrative_data)
            return saved_narrative.id
