#!/usr/bin/env python3
"""
FIKA Engineering Insights Bot - Seed Data Generator
Generates sample GitHub events for testing and demonstration
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import Database
from data_harvester import GitHubDataHarvester

def generate_and_save_seed_data():
    """Generate and save seed data to the database"""
    
    print("🌱 Generating seed data for FIKA Engineering Insights Bot...")
    
    # Initialize database
    db = Database()
    db.create_all()
    
    # Initialize data harvester with dummy token (we're using seed data)
    harvester = GitHubDataHarvester("dummy_token", db)
    
    # Generate seed events
    print("📊 Creating sample GitHub events...")
    events = harvester.generate_seed_data()
    
    # Save to database
    print(f"💾 Saving {len(events)} events to database...")
    harvester.save_events_to_db(events)
    
    print("✅ Seed data generation complete!")
    print(f"   - Generated {len(events)} GitHub events")
    print(f"   - Repository: test-org/test-repo")
    print(f"   - Events include: commits, pull requests, and CI jobs")
    print("\n🚀 You can now test the bot with `/dev-report weekly`")

def main():
    """Main entry point"""
    load_dotenv()
    
    try:
        generate_and_save_seed_data()
    except Exception as e:
        print(f"❌ Error generating seed data: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
