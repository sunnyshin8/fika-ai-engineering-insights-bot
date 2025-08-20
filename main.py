#!/usr/bin/env python3
"""
FIKA Engineering Insights Bot - Main Application
"""

import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from slack_bot import FikaSlackBot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Main entry point"""
    # Load environment variables
    load_dotenv()
    
    # Validate required environment variables
    required_vars = [
        'SLACK_BOT_TOKEN',
        'SLACK_APP_TOKEN',
        'GITHUB_TOKEN'
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("Please copy .env.example to .env and fill in your credentials")
        sys.exit(1)
    
    # Optional but recommended
    if not os.getenv('OPENAI_API_KEY'):
        logger.warning("OPENAI_API_KEY not set - AI insights will use fallback responses")
    
    try:
        # Initialize and start the bot
        bot = FikaSlackBot()
        logger.info("🚀 Starting FIKA Engineering Insights Bot...")
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Bot failed to start: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
