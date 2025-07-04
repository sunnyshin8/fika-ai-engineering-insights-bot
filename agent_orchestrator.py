from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import json
from langgraph.graph import Graph, Node, Edge
from langgraph.prebuilt import ToolNode
from langchain.tools import tool
from langchain.schema import BaseMessage, HumanMessage, AIMessage
from models import *
from database import Database
from data_harvester import GitHubDataHarvester
from diff_analyst import DiffAnalyst
from insight_narrator import InsightNarrator
import asyncio


class AgentOrchestrator:
    def __init__(self, db: Database, github_token: str, openai_api_key: str):
        self.db = db
        self.github_token = github_token
        self.openai_api_key = openai_api_key
        
        self.data_harvester = GitHubDataHarvester(github_token, db)
        self.diff_analyst = DiffAnalyst(db)
        self.insight_narrator = InsightNarrator(db, openai_api_key)
        
        self.graph = self._build_graph()
    
    def _build_graph(self) -> Graph:
        graph = Graph()
        
        graph.add_node("start", self._start_node)
        graph.add_node("data_harvester", self._data_harvester_node)
        graph.add_node("diff_analyst", self._diff_analyst_node)
        graph.add_node("insight_narrator", self._insight_narrator_node)
        graph.add_node("end", self._end_node)
        
        graph.add_edge("start", "data_harvester")
        graph.add_edge("data_harvester", "diff_analyst")
        graph.add_edge("diff_analyst", "insight_narrator")
        graph.add_edge("insight_narrator", "end")
        
        graph.set_entry_point("start")
        graph.set_finish_point("end")
        
        return graph
    
    async def process_dev_report_request(self, command: BotCommand) -> BotResponse:
        period = command.parameters.get("period", "weekly")
        repository = command.parameters.get("repository")
        author = command.parameters.get("author")
        
        initial_state = {
            "command": command.dict(),
            "period": period,
            "repository": repository,
            "author": author,
            "start_time": datetime.now(),
            "events": [],
            "metrics": None,
            "alerts": [],
            "narrative": None,
            "errors": []
        }
        
        try:
            final_state = await self.graph.ainvoke(initial_state)
            
            processing_time = (datetime.now() - initial_state["start_time"]).total_seconds() * 1000
            
            if final_state.get("narrative"):
                response_text = self._format_narrative_response(final_state["narrative"])
                attachments = self._create_response_attachments(final_state)
            else:
                response_text = "Unable to generate report. Please try again."
                attachments = []
            
            return BotResponse(
                command=command.command,
                channel_id=command.channel_id,
                user_id=command.user_id,
                response_text=response_text,
                response_type="dev_report",
                attachments=attachments,
                processing_time_ms=processing_time
            )
        
        except Exception as e:
            return BotResponse(
                command=command.command,
                channel_id=command.channel_id,
                user_id=command.user_id,
                response_text=f"Error generating report: {str(e)}",
                response_type="error",
                processing_time_ms=0
            )
    
    def _start_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["current_agent"] = "start"
        state["status"] = "initialized"
        return state
    
    def _data_harvester_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["current_agent"] = "data_harvester"
        
        try:
            period = state["period"]
            repository = state["repository"]
            
            if period == "daily":
                days_back = 1
            elif period == "weekly":
                days_back = 7
            elif period == "monthly":
                days_back = 30
            else:
                days_back = 7
            
            if repository:
                events = self.data_harvester.harvest_repository_events(repository, days_back)
            else:
                events = self.data_harvester.generate_seed_data()
            
            self.data_harvester.save_events_to_db(events)
            
            state["events"] = [event.dict() for event in events]
            state["data_harvester_status"] = "completed"
            state["events_collected"] = len(events)
            
        except Exception as e:
            state["errors"].append(f"Data harvester error: {str(e)}")
            state["data_harvester_status"] = "failed"
        
        return state
    
    def _diff_analyst_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["current_agent"] = "diff_analyst"
        
        try:
            period = MetricsPeriod(state["period"])
            
            if state["period"] == "daily":
                start_date = datetime.now() - timedelta(days=1)
                end_date = datetime.now()
            elif state["period"] == "weekly":
                start_date = datetime.now() - timedelta(weeks=1)
                end_date = datetime.now()
            elif state["period"] == "monthly":
                start_date = datetime.now() - timedelta(days=30)
                end_date = datetime.now()
            else:
                start_date = datetime.now() - timedelta(weeks=1)
                end_date = datetime.now()
            
            repository_id = 12345
            author_id = None
            
            dora_metrics = self.diff_analyst.calculate_dora_metrics(
                repository_id, period, start_date, end_date, author_id
            )
            
            churn_alerts = self.diff_analyst.analyze_code_churn(
                repository_id, period, start_date, end_date
            )
            
            risk_assessment = self.diff_analyst.generate_risk_assessment(
                churn_alerts, dora_metrics
            )
            
            state["metrics"] = dora_metrics.dict()
            state["alerts"] = [alert.dict() for alert in churn_alerts]
            state["risk_assessment"] = risk_assessment
            state["diff_analyst_status"] = "completed"
            
        except Exception as e:
            state["errors"].append(f"Diff analyst error: {str(e)}")
            state["diff_analyst_status"] = "failed"
        
        return state
    
    def _insight_narrator_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["current_agent"] = "insight_narrator"
        
        try:
            if not state.get("metrics"):
                raise ValueError("No metrics available for narrative generation")
            
            dora_metrics = DORAMetrics(**state["metrics"])
            churn_alerts = [ChurnAlert(**alert) for alert in state["alerts"]]
            risk_assessment = state["risk_assessment"]
            
            narrative = self.insight_narrator.generate_insight_narrative(
                dora_metrics, churn_alerts, risk_assessment
            )
            
            narrative_id = self.insight_narrator.save_narrative(narrative)
            
            state["narrative"] = narrative.dict()
            state["narrative_id"] = narrative_id
            state["insight_narrator_status"] = "completed"
            
        except Exception as e:
            state["errors"].append(f"Insight narrator error: {str(e)}")
            state["insight_narrator_status"] = "failed"
        
        return state
    
    def _end_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["current_agent"] = "end"
        state["status"] = "completed"
        state["end_time"] = datetime.now()
        
        total_time = (state["end_time"] - state["start_time"]).total_seconds()
        state["total_processing_time"] = total_time
        
        return state
    
    def _format_narrative_response(self, narrative_data: Dict[str, Any]) -> str:
        narrative = InsightNarrative(**narrative_data)
        
        response = f"""📊 **Engineering Productivity Report** - {narrative.period.value.title()}
📅 **Period:** {narrative.start_date.date()} to {narrative.end_date.date()}

## 📈 Summary
{narrative.summary}

## 🔍 Key Insights
"""
        
        for insight in narrative.key_insights:
            response += f"• {insight}\n"
        
        response += "\n## 📋 Recommendations\n"
        for rec in narrative.recommendations:
            response += f"• {rec}\n"
        
        if narrative.alerts:
            response += f"\n## ⚠️ Alerts ({len(narrative.alerts)})\n"
            for alert in narrative.alerts:
                response += f"• **{alert.author}**: {alert.churn_score:.1f}x churn spike ({alert.risk_level} risk)\n"
        
        response += f"\n## 📊 DORA Metrics\n"
        response += f"• **Lead Time:** {narrative.dora_metrics.lead_time_hours:.1f} hours\n"
        response += f"• **Deployment Frequency:** {narrative.dora_metrics.deployment_frequency:.2f}/day\n"
        response += f"• **Change Failure Rate:** {narrative.dora_metrics.change_failure_rate:.2%}\n"
        response += f"• **MTTR:** {narrative.dora_metrics.mean_time_to_recovery_hours:.1f} hours\n"
        
        response += f"\n## 📈 Activity\n"
        response += f"• **Commits:** {narrative.dora_metrics.commits_count}\n"
        response += f"• **Pull Requests:** {narrative.dora_metrics.pull_requests_count} ({narrative.dora_metrics.merged_prs_count} merged)\n"
        response += f"• **Code Changes:** +{narrative.dora_metrics.total_additions} -{narrative.dora_metrics.total_deletions} lines\n"
        
        return response
    
    def _create_response_attachments(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        attachments = []
        
        if state.get("metrics"):
            metrics_attachment = {
                "type": "metrics_chart",
                "title": "DORA Metrics Overview",
                "data": state["metrics"]
            }
            attachments.append(metrics_attachment)
        
        if state.get("alerts"):
            alerts_attachment = {
                "type": "alerts_table",
                "title": "Churn Alerts",
                "data": state["alerts"]
            }
            attachments.append(alerts_attachment)
        
        return attachments
    
    async def process_metrics_request(self, command: BotCommand) -> BotResponse:
        try:
            period = command.parameters.get("period", "weekly")
            repository = command.parameters.get("repository")
            author = command.parameters.get("author")
            
            if period == "daily":
                start_date = datetime.now() - timedelta(days=1)
                end_date = datetime.now()
            elif period == "weekly":
                start_date = datetime.now() - timedelta(weeks=1)
                end_date = datetime.now()
            elif period == "monthly":
                start_date = datetime.now() - timedelta(days=30)
                end_date = datetime.now()
            else:
                start_date = datetime.now() - timedelta(weeks=1)
                end_date = datetime.now()
            
            repository_id = 12345
            author_id = None
            
            dora_metrics = self.diff_analyst.calculate_dora_metrics(
                repository_id, MetricsPeriod(period), start_date, end_date, author_id
            )
            
            response_text = f"""📊 **DORA Metrics** - {period.title()}
📅 **Period:** {start_date.date()} to {end_date.date()}

**🚀 Lead Time:** {dora_metrics.lead_time_hours:.1f} hours
**📦 Deployment Frequency:** {dora_metrics.deployment_frequency:.2f}/day
**🔥 Change Failure Rate:** {dora_metrics.change_failure_rate:.2%}
**⏱️ Mean Time to Recovery:** {dora_metrics.mean_time_to_recovery_hours:.1f} hours

**📈 Activity:**
• Commits: {dora_metrics.commits_count}
• Pull Requests: {dora_metrics.pull_requests_count} ({dora_metrics.merged_prs_count} merged)
• Code Changes: +{dora_metrics.total_additions} -{dora_metrics.total_deletions} lines
• Churn Score: {dora_metrics.churn_score:.1f}"""
            
            return BotResponse(
                command=command.command,
                channel_id=command.channel_id,
                user_id=command.user_id,
                response_text=response_text,
                response_type="metrics",
                attachments=[{"type": "metrics", "data": dora_metrics.dict()}]
            )
        
        except Exception as e:
            return BotResponse(
                command=command.command,
                channel_id=command.channel_id,
                user_id=command.user_id,
                response_text=f"Error fetching metrics: {str(e)}",
                response_type="error"
            )
    
    def get_agent_status(self) -> Dict[str, Any]:
        return {
            "orchestrator_status": "active",
            "agents": {
                "data_harvester": "ready",
                "diff_analyst": "ready",
                "insight_narrator": "ready"
            },
            "graph_nodes": len(self.graph.nodes),
            "graph_edges": len(self.graph.edges)
        }
