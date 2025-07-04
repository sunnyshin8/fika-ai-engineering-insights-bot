import sqlite3
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Boolean, Text, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
import json

Base = declarative_base()


class DBRepository(Base):
    __tablename__ = "repositories"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    full_name = Column(String(512), nullable=False, unique=True)
    owner = Column(String(255), nullable=False)
    default_branch = Column(String(100), default="main")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class DBAuthor(Base):
    __tablename__ = "authors"
    
    id = Column(Integer, primary_key=True)
    login = Column(String(255), nullable=False, unique=True)
    name = Column(String(255))
    email = Column(String(255))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class DBCommit(Base):
    __tablename__ = "commits"
    
    id = Column(Integer, primary_key=True)
    sha = Column(String(40), nullable=False, unique=True)
    message = Column(Text)
    author_id = Column(Integer, ForeignKey("authors.id"))
    repository_id = Column(Integer, ForeignKey("repositories.id"))
    timestamp = Column(DateTime, nullable=False)
    url = Column(String(512))
    additions = Column(Integer, default=0)
    deletions = Column(Integer, default=0)
    changed_files = Column(Integer, default=0)
    parents = Column(SQLiteJSON)
    created_at = Column(DateTime, default=datetime.now)
    
    author = relationship("DBAuthor")
    repository = relationship("DBRepository")


class DBPullRequest(Base):
    __tablename__ = "pull_requests"
    
    id = Column(Integer, primary_key=True)
    github_id = Column(Integer, nullable=False)
    number = Column(Integer, nullable=False)
    title = Column(String(512))
    state = Column(String(50))
    author_id = Column(Integer, ForeignKey("authors.id"))
    repository_id = Column(Integer, ForeignKey("repositories.id"))
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    closed_at = Column(DateTime)
    merged_at = Column(DateTime)
    draft = Column(Boolean, default=False)
    url = Column(String(512))
    base_branch = Column(String(255))
    head_branch = Column(String(255))
    commits_count = Column(Integer, default=0)
    changed_files = Column(Integer, default=0)
    additions = Column(Integer, default=0)
    deletions = Column(Integer, default=0)
    
    author = relationship("DBAuthor")
    repository = relationship("DBRepository")


class DBPullRequestReview(Base):
    __tablename__ = "pull_request_reviews"
    
    id = Column(Integer, primary_key=True)
    github_id = Column(Integer, nullable=False)
    pull_request_id = Column(Integer, ForeignKey("pull_requests.id"))
    author_id = Column(Integer, ForeignKey("authors.id"))
    state = Column(String(50))
    submitted_at = Column(DateTime, nullable=False)
    body = Column(Text)
    
    author = relationship("DBAuthor")


class DBCIJob(Base):
    __tablename__ = "ci_jobs"
    
    id = Column(Integer, primary_key=True)
    github_id = Column(String(255), nullable=False)
    name = Column(String(255))
    status = Column(String(50))
    conclusion = Column(String(50))
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime)
    repository_id = Column(Integer, ForeignKey("repositories.id"))
    commit_sha = Column(String(40))
    pull_request_id = Column(Integer, ForeignKey("pull_requests.id"))
    url = Column(String(512))
    
    repository = relationship("DBRepository")


class DBGitHubEvent(Base):
    __tablename__ = "github_events"
    
    id = Column(Integer, primary_key=True)
    github_id = Column(String(255), nullable=False)
    event_type = Column(String(100), nullable=False)
    timestamp = Column(DateTime, nullable=False)
    repository_id = Column(Integer, ForeignKey("repositories.id"))
    actor_id = Column(Integer, ForeignKey("authors.id"))
    payload = Column(SQLiteJSON)
    raw_data = Column(SQLiteJSON)
    created_at = Column(DateTime, default=datetime.now)
    
    repository = relationship("DBRepository")
    actor = relationship("DBAuthor")


class DBMetrics(Base):
    __tablename__ = "metrics"
    
    id = Column(Integer, primary_key=True)
    period = Column(String(50), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    repository_id = Column(Integer, ForeignKey("repositories.id"))
    author_id = Column(Integer, ForeignKey("authors.id"))
    
    lead_time_hours = Column(Float, default=0.0)
    deployment_frequency = Column(Float, default=0.0)
    change_failure_rate = Column(Float, default=0.0)
    mean_time_to_recovery_hours = Column(Float, default=0.0)
    
    commits_count = Column(Integer, default=0)
    pull_requests_count = Column(Integer, default=0)
    merged_prs_count = Column(Integer, default=0)
    review_time_hours = Column(Float, default=0.0)
    cycle_time_hours = Column(Float, default=0.0)
    ci_failures_count = Column(Integer, default=0)
    
    total_additions = Column(Integer, default=0)
    total_deletions = Column(Integer, default=0)
    total_files_changed = Column(Integer, default=0)
    churn_score = Column(Float, default=0.0)
    
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    repository = relationship("DBRepository")
    author = relationship("DBAuthor")


class DBChurnAlert(Base):
    __tablename__ = "churn_alerts"
    
    id = Column(Integer, primary_key=True)
    author_id = Column(Integer, ForeignKey("authors.id"))
    repository_id = Column(Integer, ForeignKey("repositories.id"))
    period = Column(String(50), nullable=False)
    churn_score = Column(Float, nullable=False)
    threshold = Column(Float, nullable=False)
    is_spike = Column(Boolean, default=False)
    previous_average = Column(Float, default=0.0)
    current_period_churn = Column(Float, default=0.0)
    risk_level = Column(String(50))
    created_at = Column(DateTime, default=datetime.now)
    
    author = relationship("DBAuthor")
    repository = relationship("DBRepository")


class DBInsightNarrative(Base):
    __tablename__ = "insight_narratives"
    
    id = Column(Integer, primary_key=True)
    period = Column(String(50), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    repository_id = Column(Integer, ForeignKey("repositories.id"))
    author_id = Column(Integer, ForeignKey("authors.id"))
    
    summary = Column(Text)
    key_insights = Column(SQLiteJSON)
    recommendations = Column(SQLiteJSON)
    alerts = Column(SQLiteJSON)
    
    dora_metrics_id = Column(Integer, ForeignKey("metrics.id"))
    
    created_at = Column(DateTime, default=datetime.now)
    llm_model = Column(String(100), default="gpt-3.5-turbo")
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    
    repository = relationship("DBRepository")
    author = relationship("DBAuthor")
    dora_metrics = relationship("DBMetrics")


class DBBotCommand(Base):
    __tablename__ = "bot_commands"
    
    id = Column(Integer, primary_key=True)
    command = Column(String(255), nullable=False)
    channel_id = Column(String(255), nullable=False)
    user_id = Column(String(255), nullable=False)
    user_name = Column(String(255))
    timestamp = Column(DateTime, nullable=False)
    parameters = Column(SQLiteJSON)
    created_at = Column(DateTime, default=datetime.now)


class DBBotResponse(Base):
    __tablename__ = "bot_responses"
    
    id = Column(Integer, primary_key=True)
    command_id = Column(Integer, ForeignKey("bot_commands.id"))
    channel_id = Column(String(255), nullable=False)
    user_id = Column(String(255), nullable=False)
    response_text = Column(Text)
    response_type = Column(String(100))
    attachments = Column(SQLiteJSON)
    timestamp = Column(DateTime, default=datetime.now)
    processing_time_ms = Column(Float, default=0.0)
    
    command = relationship("DBBotCommand")


class Database:
    def __init__(self, database_url: str = "sqlite:///fika_bot.db"):
        self.engine = create_engine(database_url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.create_tables()
    
    def create_tables(self):
        Base.metadata.create_all(bind=self.engine)
    
    def get_session(self) -> Session:
        return self.SessionLocal()
    
    def get_or_create_author(self, session: Session, login: str, name: str = None, email: str = None) -> DBAuthor:
        author = session.query(DBAuthor).filter_by(login=login).first()
        if not author:
            author = DBAuthor(login=login, name=name, email=email)
            session.add(author)
            session.commit()
        return author
    
    def get_or_create_repository(self, session: Session, github_id: int, name: str, full_name: str, owner: str) -> DBRepository:
        repo = session.query(DBRepository).filter_by(id=github_id).first()
        if not repo:
            repo = DBRepository(id=github_id, name=name, full_name=full_name, owner=owner)
            session.add(repo)
            session.commit()
        return repo
    
    def save_commit(self, session: Session, commit_data: dict) -> DBCommit:
        author = self.get_or_create_author(session, commit_data["author"]["login"], 
                                         commit_data["author"].get("name"), 
                                         commit_data["author"].get("email"))
        repo = self.get_or_create_repository(session, commit_data["repository"]["id"],
                                           commit_data["repository"]["name"],
                                           commit_data["repository"]["full_name"],
                                           commit_data["repository"]["owner"])
        
        commit = DBCommit(
            sha=commit_data["sha"],
            message=commit_data["message"],
            author_id=author.id,
            repository_id=repo.id,
            timestamp=commit_data["timestamp"],
            url=commit_data["url"],
            additions=commit_data["diff_stats"]["additions"],
            deletions=commit_data["diff_stats"]["deletions"],
            changed_files=commit_data["diff_stats"]["changed_files"],
            parents=commit_data.get("parents", [])
        )
        session.add(commit)
        session.commit()
        return commit
    
    def save_pull_request(self, session: Session, pr_data: dict) -> DBPullRequest:
        author = self.get_or_create_author(session, pr_data["author"]["login"])
        repo = self.get_or_create_repository(session, pr_data["repository"]["id"],
                                           pr_data["repository"]["name"],
                                           pr_data["repository"]["full_name"],
                                           pr_data["repository"]["owner"])
        
        pr = DBPullRequest(
            github_id=pr_data["id"],
            number=pr_data["number"],
            title=pr_data["title"],
            state=pr_data["state"],
            author_id=author.id,
            repository_id=repo.id,
            created_at=pr_data["created_at"],
            updated_at=pr_data["updated_at"],
            closed_at=pr_data.get("closed_at"),
            merged_at=pr_data.get("merged_at"),
            draft=pr_data.get("draft", False),
            url=pr_data["url"],
            base_branch=pr_data["base_branch"],
            head_branch=pr_data["head_branch"],
            commits_count=pr_data["commits_count"],
            changed_files=pr_data["changed_files"],
            additions=pr_data["diff_stats"]["additions"],
            deletions=pr_data["diff_stats"]["deletions"]
        )
        session.add(pr)
        session.commit()
        return pr
    
    def get_metrics(self, session: Session, period: str, start_date: datetime, end_date: datetime,
                   repository_id: int = None, author_id: int = None) -> List[DBMetrics]:
        query = session.query(DBMetrics).filter(
            DBMetrics.period == period,
            DBMetrics.start_date >= start_date,
            DBMetrics.end_date <= end_date
        )
        
        if repository_id:
            query = query.filter(DBMetrics.repository_id == repository_id)
        if author_id:
            query = query.filter(DBMetrics.author_id == author_id)
        
        return query.all()
    
    def save_metrics(self, session: Session, metrics_data: dict) -> DBMetrics:
        metrics = DBMetrics(**metrics_data)
        session.add(metrics)
        session.commit()
        return metrics
    
    def save_churn_alert(self, session: Session, alert_data: dict) -> DBChurnAlert:
        alert = DBChurnAlert(**alert_data)
        session.add(alert)
        session.commit()
        return alert
    
    def save_insight_narrative(self, session: Session, narrative_data: dict) -> DBInsightNarrative:
        narrative = DBInsightNarrative(**narrative_data)
        session.add(narrative)
        session.commit()
        return narrative
    
    def save_bot_command(self, session: Session, command_data: dict) -> DBBotCommand:
        command = DBBotCommand(**command_data)
        session.add(command)
        session.commit()
        return command
    
    def save_bot_response(self, session: Session, response_data: dict) -> DBBotResponse:
        response = DBBotResponse(**response_data)
        session.add(response)
        session.commit()
        return response
