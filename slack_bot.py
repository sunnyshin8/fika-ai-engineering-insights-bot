import os
import logging
import asyncio
import json
from datetime import datetime
from typing import Dict, Any
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
import matplotlib.pyplot as plt
import io
import base64

from agents import EngineeringInsightsOrchestrator
from models import MetricsPeriod
from database import Database

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FikaSlackBot:
    def __init__(self):
        # Load environment variables
        self.slack_bot_token = os.getenv("SLACK_BOT_TOKEN")
        self.slack_app_token = os.getenv("SLACK_APP_TOKEN")
        self.github_token = os.getenv("GITHUB_TOKEN")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.default_repo = os.getenv("DEFAULT_REPO", "test-org/test-repo")
        
        # Validate required environment variables
        if not all([self.slack_bot_token, self.slack_app_token, self.github_token]):
            raise ValueError("Missing required environment variables. Check SLACK_BOT_TOKEN, SLACK_APP_TOKEN, and GITHUB_TOKEN")
        
        # Initialize Slack app
        self.app = AsyncApp(token=self.slack_bot_token)
        
        # Initialize orchestrator
        self.orchestrator = EngineeringInsightsOrchestrator(
            github_token=self.github_token,
            openai_api_key=self.openai_api_key
        )
        
        # Setup command handlers
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Setup Slack command handlers"""
        
        @self.app.command("/dev-report")
        async def handle_dev_report(ack, respond, command):
            await ack()
            
            # Parse command parameters
            text = command.get('text', '').strip()
            params = self._parse_command_params(text)
            
            # Default values
            period = params.get('period', 'weekly')
            repository = params.get('repo', self.default_repo)
            
            # Validate period
            try:
                period_enum = MetricsPeriod(period.lower())
            except ValueError:
                await respond(f"❌ Invalid period '{period}'. Use: daily, weekly, or monthly")
                return
            
            # Send initial response
            await respond(f"🔄 Generating {period} development report for `{repository}`...")
            
            try:
                # Generate insights using the orchestrator
                results = await self.orchestrator.generate_insights(
                    repository=repository,
                    period=period_enum
                )
                
                # Format and send the response
                await self._send_insights_report(respond, results)
                
            except Exception as e:
                logger.error(f"Error generating report: {e}")
                await respond(f"❌ Failed to generate report: {str(e)}")
        
        @self.app.command("/dev-help")
        async def handle_help(ack, respond, command):
            await ack()
            help_text = self._get_help_text()
            await respond(help_text)
        
        @self.app.event("app_mention")
        async def handle_app_mention(event, say):
            """Handle @mentions of the bot"""
            user_id = event["user"]
            text = event.get("text", "")
            
            if "help" in text.lower():
                await say(f"<@{user_id}> " + self._get_help_text())
            elif "report" in text.lower():
                await say(f"<@{user_id}> Use `/dev-report weekly` to generate a development report!")
            else:
                await say(f"<@{user_id}> Hi! I'm the FIKA Engineering Insights Bot. Use `/dev-help` for commands.")
    
    def _parse_command_params(self, text: str) -> Dict[str, str]:
        """Parse command parameters from text"""
        params = {}
        parts = text.split()
        
        for part in parts:
            if part.lower() in ['daily', 'weekly', 'monthly']:
                params['period'] = part.lower()
            elif '/' in part and len(part.split('/')) == 2:
                params['repo'] = part
        
        return params
    
    async def _send_insights_report(self, respond, results: Dict[str, Any]):
        """Format and send the insights report to Slack"""
        
        narrative = results.get('narrative')
        dora_metrics = results.get('dora_metrics')
        risk_assessment = results.get('risk_assessment', {})
        messages = results.get('messages', [])
        
        # Create main report blocks
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📊 {results['period'].title()} Development Report"
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Repository:* `{results['repository']}` | *Generated:* {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                    }
                ]
            },
            {
                "type": "divider"
            }
        ]
        
        # Add summary
        if narrative and narrative.summary:
            blocks.extend([
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*📋 Executive Summary*\n{narrative.summary}"
                    }
                },
                {
                    "type": "divider"
                }
            ])
        
        # Add DORA metrics
        if dora_metrics:
            metrics_text = self._format_dora_metrics(dora_metrics)
            blocks.extend([
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*📈 DORA Metrics*\n{metrics_text}"
                    }
                },
                {
                    "type": "divider"
                }
            ])
        
        # Add key insights
        if narrative and narrative.key_insights:
            insights_text = "\n".join([f"• {insight}" for insight in narrative.key_insights])
            blocks.extend([
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*💡 Key Insights*\n{insights_text}"
                    }
                },
                {
                    "type": "divider"
                }
            ])
        
        # Add recommendations
        if narrative and narrative.recommendations:
            recommendations_text = "\n".join([f"• {rec}" for rec in narrative.recommendations])
            blocks.extend([
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*🎯 Recommendations*\n{recommendations_text}"
                    }
                },
                {
                    "type": "divider"
                }
            ])
        
        # Add risk assessment
        risk_level = risk_assessment.get('overall_risk_level', 'unknown')
        risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴", "critical": "🚨"}.get(risk_level, "⚪")
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*⚠️ Risk Assessment*\n{risk_emoji} Overall Risk Level: *{risk_level.title()}*"
            }
        })
        
        # Add processing messages for transparency
        if messages:
            process_text = "\n".join([f"• {msg}" for msg in messages[-3:]])  
            blocks.extend([
                {
                    "type": "divider"
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"*🔍 Processing Log:*\n{process_text}"
                        }
                    ]
                }
            ])
        
        # Send the report
        await respond(
            text=f"Development Report for {results['repository']}",
            blocks=blocks
        )
    
    def _format_dora_metrics(self, metrics) -> str:
        """Format DORA metrics for display"""
        
        # Handle both dict and object formats
        if hasattr(metrics, '__dict__'):
            m = metrics.__dict__
        else:
            m = metrics
        
        return f"""
• *Lead Time:* {m.get('lead_time_hours', 0):.1f} hours
• *Deployment Frequency:* {m.get('deployment_frequency', 0):.1f} deploys/day
• *Change Failure Rate:* {m.get('change_failure_rate', 0):.1%}
• *Mean Time to Recovery:* {m.get('mean_time_to_recovery_hours', 0):.1f} hours
• *Commits:* {m.get('commits_count', 0)}
• *Pull Requests:* {m.get('pull_requests_count', 0)} ({m.get('merged_prs_count', 0)} merged)
• *Code Churn:* +{m.get('total_additions', 0)} -{m.get('total_deletions', 0)} lines
• *Files Changed:* {m.get('total_files_changed', 0)}
        """.strip()
    
    def _get_help_text(self) -> str:
        """Get help text for the bot"""
        return """
*🤖 FIKA Engineering Insights Bot*

*Available Commands:*
• `/dev-report weekly` - Generate weekly development report
• `/dev-report daily` - Generate daily development report  
• `/dev-report monthly` - Generate monthly development report
• `/dev-report weekly repo owner/repo-name` - Report for specific repository
• `/dev-help` - Show this help message

*Examples:*
• `/dev-report weekly`
• `/dev-report daily repo myorg/myproject`

The bot analyzes GitHub activity and generates AI-powered insights about:
📊 DORA metrics (lead time, deployment frequency, change failure rate, MTTR)
🔍 Code churn analysis and risk assessment
💡 AI-generated insights and recommendations
⚠️ Automated alerts for concerning patterns

*Need help?* Mention me with @fikabot and I'll assist you!
        """.strip()
    
    async def start(self):
        """Start the Slack bot"""
        handler = AsyncSocketModeHandler(self.app, self.slack_app_token)
        logger.info("🚀 Starting FIKA Engineering Insights Bot...")
        await handler.start_async()

if __name__ == "__main__":
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    bot = FikaSlackBot()
    asyncio.run(bot.start())
