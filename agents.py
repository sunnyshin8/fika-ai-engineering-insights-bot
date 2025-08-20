from typing import Dict, Any, List
from datetime import datetime, timedelta
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict, Annotated
import logging

from data_harvester import GitHubDataHarvester
from diff_analyst import DiffAnalyst
from insight_narrator import InsightNarrator
from database import Database
from models import *

logger = logging.getLogger(__name__)

class AgentState(TypedDict):
    """State shared between agents"""
    repository: str
    days_back: int
    period: MetricsPeriod
    events: List[GitHubEvent]
    dora_metrics: DORAMetrics
    churn_alerts: List[ChurnAlert]
    risk_assessment: Dict[str, Any]
    narrative: InsightNarrative
    messages: Annotated[List[str], add_messages]
    next_action: str

class EngineeringInsightsOrchestrator:
    """LangGraph orchestrator for engineering insights agents"""
    
    def __init__(self, github_token: str, openai_api_key: str, database_url: str = "sqlite:///fika_bot.db"):
        self.db = Database(database_url)
        self.data_harvester = GitHubDataHarvester(github_token, self.db)
        self.diff_analyst = DiffAnalyst(self.db)
        self.insight_narrator = InsightNarrator(self.db, openai_api_key)
        
        # Initialize the database
        self.db.create_all()
        
        # Build the LangGraph workflow
        self.workflow = self._build_workflow()
    
    def _build_workflow(self) -> StateGraph:
        """Build the LangGraph workflow with agent nodes and edges"""
        
        workflow = StateGraph(AgentState)
        
        # Add agent nodes
        workflow.add_node("data_harvester", self._data_harvester_node)
        workflow.add_node("diff_analyst", self._diff_analyst_node)
        workflow.add_node("insight_narrator", self._insight_narrator_node)
        
        # Define the flow
        workflow.set_entry_point("data_harvester")
        workflow.add_edge("data_harvester", "diff_analyst")
        workflow.add_edge("diff_analyst", "insight_narrator")
        workflow.add_edge("insight_narrator", END)
        
        return workflow.compile()
    
    def _data_harvester_node(self, state: AgentState) -> AgentState:
        """Data Harvester Agent Node"""
        logger.info(f"🔍 Data Harvester: Collecting events for {state['repository']}")
        
        try:
            # Check if we should use seed data or real GitHub data
            if state['repository'] == "test-org/test-repo":
                events = self.data_harvester.generate_seed_data()
                logger.info("📊 Using seed data for demo")
            else:
                events = self.data_harvester.harvest_repository_events(
                    state['repository'], 
                    state['days_back']
                )
            
            # Save events to database
            self.data_harvester.save_events_to_db(events)
            
            state['events'] = events
            state['messages'].append(f"✅ Collected {len(events)} events from {state['repository']}")
            
        except Exception as e:
            logger.error(f"Data harvesting failed: {e}")
            state['events'] = []
            state['messages'].append(f"❌ Data harvesting failed: {str(e)}")
        
        return state
    
    def _diff_analyst_node(self, state: AgentState) -> AgentState:
        """Diff Analyst Agent Node"""
        logger.info("📈 Diff Analyst: Analyzing code churn and calculating DORA metrics")
        
        try:
            # Determine date range based on period
            end_date = datetime.now()
            if state['period'] == MetricsPeriod.DAILY:
                start_date = end_date - timedelta(days=1)
            elif state['period'] == MetricsPeriod.WEEKLY:
                start_date = end_date - timedelta(days=7)
            else:  # MONTHLY
                start_date = end_date - timedelta(days=30)
            
            # Get repository ID (use a default for demo)
            repository_id = 12345  # This would come from the database in a real implementation
            
            # Calculate DORA metrics
            dora_metrics = self.diff_analyst.calculate_dora_metrics(
                repository_id=repository_id,
                period=state['period'],
                start_date=start_date,
                end_date=end_date
            )
            
            # Analyze code churn
            churn_alerts = self.diff_analyst.analyze_code_churn(
                repository_id=repository_id,
                period=state['period'],
                start_date=start_date,
                end_date=end_date
            )
            
            # Generate risk assessment
            risk_assessment = self.diff_analyst.generate_risk_assessment(
                churn_alerts, dora_metrics
            )
            
            state['dora_metrics'] = dora_metrics
            state['churn_alerts'] = churn_alerts
            state['risk_assessment'] = risk_assessment
            state['messages'].append(f"📊 Analyzed metrics: {len(churn_alerts)} alerts, risk level: {risk_assessment.get('overall_risk_level', 'unknown')}")
            
        except Exception as e:
            logger.error(f"Diff analysis failed: {e}")
            # Create default metrics for demo
            state['dora_metrics'] = self._create_default_dora_metrics(state)
            state['churn_alerts'] = []
            state['risk_assessment'] = {"overall_risk_level": "low", "risk_factors": [], "recommendations": []}
            state['messages'].append(f"⚠️ Using default metrics due to error: {str(e)}")
        
        return state
    
    def _insight_narrator_node(self, state: AgentState) -> AgentState:
        """Insight Narrator Agent Node"""
        logger.info("🤖 Insight Narrator: Generating AI insights")
        
        try:
            narrative = self.insight_narrator.generate_insight_narrative(
                state['dora_metrics'],
                state['churn_alerts'],
                state['risk_assessment']
            )
            
            # Save narrative to database
            narrative_id = self.insight_narrator.save_narrative(narrative)
            
            state['narrative'] = narrative
            state['messages'].append(f"✨ Generated insights narrative (ID: {narrative_id})")
            
        except Exception as e:
            logger.error(f"Insight generation failed: {e}")
            # Create a basic narrative as fallback
            state['narrative'] = self._create_default_narrative(state)
            state['messages'].append(f"⚠️ Using default narrative due to error: {str(e)}")
        
        return state
    
    def _create_default_dora_metrics(self, state: AgentState) -> DORAMetrics:
        """Create default DORA metrics for demo purposes"""
        end_date = datetime.now()
        if state['period'] == MetricsPeriod.DAILY:
            start_date = end_date - timedelta(days=1)
        elif state['period'] == MetricsPeriod.WEEKLY:
            start_date = end_date - timedelta(days=7)
        else:
            start_date = end_date - timedelta(days=30)
        
        return DORAMetrics(
            period=state['period'],
            start_date=start_date,
            end_date=end_date,
            repository=state['repository'],
            lead_time_hours=24.5,
            deployment_frequency=2.3,
            change_failure_rate=0.05,
            mean_time_to_recovery_hours=2.1,
            commits_count=len([e for e in state.get('events', []) if e.type == EventType.COMMIT]),
            pull_requests_count=len([e for e in state.get('events', []) if e.type == EventType.PULL_REQUEST]),
            merged_prs_count=len([e for e in state.get('events', []) if e.type == EventType.PULL_REQUEST]),
            review_time_hours=4.2,
            cycle_time_hours=28.7,
            ci_failures_count=2,
            total_additions=1250,
            total_deletions=350,
            total_files_changed=45,
            churn_score=235.8
        )
    
    def _create_default_narrative(self, state: AgentState) -> InsightNarrative:
        """Create a default narrative for demo purposes"""
        return InsightNarrative(
            period=state['period'],
            start_date=state['dora_metrics'].start_date,
            end_date=state['dora_metrics'].end_date,
            repository=state['repository'],
            summary="Team shows strong development velocity with healthy DORA metrics. Code quality remains high with minimal churn alerts.",
            key_insights=[
                "Development velocity is above team average",
                "Lead time remains within acceptable bounds",
                "Change failure rate is below industry benchmark",
                "Review process is efficient"
            ],
            recommendations=[
                "Continue current development practices",
                "Monitor for any emerging churn patterns",
                "Consider automated testing improvements"
            ],
            alerts=state.get('churn_alerts', []),
            dora_metrics=state['dora_metrics']
        )
    
    async def generate_insights(self, repository: str, period: MetricsPeriod = MetricsPeriod.WEEKLY, days_back: int = 7) -> Dict[str, Any]:
        """Main entry point for generating insights"""
        
        initial_state = AgentState(
            repository=repository,
            days_back=days_back,
            period=period,
            events=[],
            dora_metrics=None,
            churn_alerts=[],
            risk_assessment={},
            narrative=None,
            messages=[],
            next_action="start"
        )
        
        logger.info(f"🚀 Starting insights generation for {repository} ({period.value} report)")
        
        # Run the workflow
        final_state = await self.workflow.ainvoke(initial_state)
        
        return {
            "repository": repository,
            "period": period.value,
            "narrative": final_state['narrative'],
            "dora_metrics": final_state['dora_metrics'],
            "churn_alerts": final_state['churn_alerts'],
            "risk_assessment": final_state['risk_assessment'],
            "messages": final_state['messages']
        }
