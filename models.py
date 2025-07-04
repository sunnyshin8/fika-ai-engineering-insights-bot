from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class EventType(str, Enum):
    COMMIT = "commit"
    PULL_REQUEST = "pull_request"
    PULL_REQUEST_REVIEW = "pull_request_review"
    PUSH = "push"
    CI_FAILURE = "ci_failure"


class DiffStat(BaseModel):
    additions: int = 0
    deletions: int = 0
    changed_files: int = 0


class Author(BaseModel):
    login: str
    name: Optional[str] = None
    email: Optional[str] = None


class Repository(BaseModel):
    id: int
    name: str
    full_name: str
    owner: str
    default_branch: str = "main"


class Commit(BaseModel):
    sha: str
    message: str
    author: Author
    timestamp: datetime
    repository: Repository
    diff_stats: DiffStat
    url: str
    parents: List[str] = []


class PullRequest(BaseModel):
    id: int
    number: int
    title: str
    state: str
    author: Author
    repository: Repository
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime] = None
    merged_at: Optional[datetime] = None
    draft: bool = False
    diff_stats: DiffStat
    url: str
    base_branch: str
    head_branch: str
    commits_count: int = 0
    changed_files: int = 0


class PullRequestReview(BaseModel):
    id: int
    pull_request_id: int
    author: Author
    state: str
    submitted_at: datetime
    body: Optional[str] = None


class CIJob(BaseModel):
    id: str
    name: str
    status: str
    conclusion: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    repository: Repository
    commit_sha: str
    pull_request_id: Optional[int] = None
    url: str


class GitHubEvent(BaseModel):
    id: str
    type: EventType
    timestamp: datetime
    repository: Repository
    actor: Author
    payload: Dict[str, Any]
    raw_data: Dict[str, Any] = {}


class MetricsPeriod(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class DORAMetrics(BaseModel):
    period: MetricsPeriod
    start_date: datetime
    end_date: datetime
    repository: Optional[str] = None
    author: Optional[str] = None
    
    lead_time_hours: float = 0.0
    deployment_frequency: float = 0.0
    change_failure_rate: float = 0.0
    mean_time_to_recovery_hours: float = 0.0
    
    commits_count: int = 0
    pull_requests_count: int = 0
    merged_prs_count: int = 0
    review_time_hours: float = 0.0
    cycle_time_hours: float = 0.0
    ci_failures_count: int = 0
    
    total_additions: int = 0
    total_deletions: int = 0
    total_files_changed: int = 0
    churn_score: float = 0.0


class ChurnAlert(BaseModel):
    author: str
    repository: str
    period: MetricsPeriod
    churn_score: float
    threshold: float
    is_spike: bool
    previous_average: float
    current_period_churn: float
    risk_level: str


class InsightNarrative(BaseModel):
    period: MetricsPeriod
    start_date: datetime
    end_date: datetime
    repository: Optional[str] = None
    author: Optional[str] = None
    
    summary: str
    key_insights: List[str]
    recommendations: List[str]
    alerts: List[ChurnAlert]
    
    dora_metrics: DORAMetrics
    created_at: datetime = Field(default_factory=datetime.now)
    llm_model: str = "gpt-3.5-turbo"
    prompt_tokens: int = 0
    completion_tokens: int = 0


class BotCommand(BaseModel):
    command: str
    channel_id: str
    user_id: str
    user_name: str
    timestamp: datetime
    parameters: Dict[str, Any] = {}


class BotResponse(BaseModel):
    command: str
    channel_id: str
    user_id: str
    response_text: str
    response_type: str
    attachments: List[Dict[str, Any]] = []
    timestamp: datetime = Field(default_factory=datetime.now)
    processing_time_ms: float = 0.0


class AgentState(BaseModel):
    conversation_id: str
    current_agent: str
    data: Dict[str, Any] = {}
    context: Dict[str, Any] = {}
    next_action: Optional[str] = None
    completed_actions: List[str] = []
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class DataHarvesterState(BaseModel):
    repositories: List[str] = []
    date_range: Dict[str, datetime] = {}
    events_collected: int = 0
    last_sync: Optional[datetime] = None
    errors: List[str] = []


class DiffAnalystState(BaseModel):
    commits_analyzed: int = 0
    churn_alerts: List[ChurnAlert] = []
    risk_analysis_complete: bool = False
    analysis_summary: Dict[str, Any] = {}


class InsightNarratorState(BaseModel):
    narratives_generated: int = 0
    current_narrative: Optional[InsightNarrative] = None
    generation_complete: bool = False
    review_required: bool = False
