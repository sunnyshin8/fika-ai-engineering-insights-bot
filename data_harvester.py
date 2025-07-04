from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from github import Github
import requests
from models import *
from database import Database
import os
import json


class GitHubDataHarvester:
    def __init__(self, token: str, db: Database):
        self.github = Github(token)
        self.db = db
        self.token = token
        self.headers = {"Authorization": f"token {token}"}
    
    def harvest_repository_events(self, repo_name: str, days_back: int = 7) -> List[GitHubEvent]:
        events = []
        repo = self.github.get_repo(repo_name)
        
        since_date = datetime.now() - timedelta(days=days_back)
        
        events.extend(self._harvest_commits(repo, since_date))
        events.extend(self._harvest_pull_requests(repo, since_date))
        events.extend(self._harvest_ci_jobs(repo, since_date))
        
        return events
    
    def _harvest_commits(self, repo, since_date: datetime) -> List[GitHubEvent]:
        events = []
        commits = repo.get_commits(since=since_date)
        
        for commit in commits:
            try:
                commit_data = self._get_commit_with_stats(repo, commit.sha)
                if commit_data:
                    event = GitHubEvent(
                        id=f"commit_{commit.sha}",
                        type=EventType.COMMIT,
                        timestamp=commit.commit.author.date,
                        repository=Repository(
                            id=repo.id,
                            name=repo.name,
                            full_name=repo.full_name,
                            owner=repo.owner.login
                        ),
                        actor=Author(
                            login=commit.author.login if commit.author else "unknown",
                            name=commit.commit.author.name,
                            email=commit.commit.author.email
                        ),
                        payload=commit_data,
                        raw_data=commit.raw_data
                    )
                    events.append(event)
            except Exception as e:
                print(f"Error processing commit {commit.sha}: {e}")
        
        return events
    
    def _harvest_pull_requests(self, repo, since_date: datetime) -> List[GitHubEvent]:
        events = []
        pulls = repo.get_pulls(state="all", sort="updated", direction="desc")
        
        for pr in pulls:
            if pr.updated_at < since_date:
                break
                
            try:
                pr_data = self._get_pr_with_stats(repo, pr.number)
                if pr_data:
                    event = GitHubEvent(
                        id=f"pr_{pr.id}",
                        type=EventType.PULL_REQUEST,
                        timestamp=pr.updated_at,
                        repository=Repository(
                            id=repo.id,
                            name=repo.name,
                            full_name=repo.full_name,
                            owner=repo.owner.login
                        ),
                        actor=Author(
                            login=pr.user.login,
                            name=pr.user.name
                        ),
                        payload=pr_data,
                        raw_data=pr.raw_data
                    )
                    events.append(event)
                    
                    reviews = pr.get_reviews()
                    for review in reviews:
                        if review.submitted_at >= since_date:
                            review_event = GitHubEvent(
                                id=f"review_{review.id}",
                                type=EventType.PULL_REQUEST_REVIEW,
                                timestamp=review.submitted_at,
                                repository=Repository(
                                    id=repo.id,
                                    name=repo.name,
                                    full_name=repo.full_name,
                                    owner=repo.owner.login
                                ),
                                actor=Author(
                                    login=review.user.login,
                                    name=review.user.name
                                ),
                                payload={
                                    "review_id": review.id,
                                    "pull_request_id": pr.id,
                                    "state": review.state,
                                    "body": review.body
                                },
                                raw_data=review.raw_data
                            )
                            events.append(review_event)
            except Exception as e:
                print(f"Error processing PR {pr.number}: {e}")
        
        return events
    
    def _harvest_ci_jobs(self, repo, since_date: datetime) -> List[GitHubEvent]:
        events = []
        
        try:
            url = f"https://api.github.com/repos/{repo.full_name}/actions/runs"
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                runs = response.json().get("workflow_runs", [])
                
                for run in runs:
                    run_date = datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))
                    if run_date < since_date:
                        break
                    
                    if run["conclusion"] == "failure":
                        event = GitHubEvent(
                            id=f"ci_failure_{run['id']}",
                            type=EventType.CI_FAILURE,
                            timestamp=run_date,
                            repository=Repository(
                                id=repo.id,
                                name=repo.name,
                                full_name=repo.full_name,
                                owner=repo.owner.login
                            ),
                            actor=Author(
                                login=run["actor"]["login"],
                                name=run["actor"]["login"]
                            ),
                            payload={
                                "run_id": run["id"],
                                "name": run["name"],
                                "status": run["status"],
                                "conclusion": run["conclusion"],
                                "head_sha": run["head_sha"]
                            },
                            raw_data=run
                        )
                        events.append(event)
        except Exception as e:
            print(f"Error fetching CI jobs: {e}")
        
        return events
    
    def _get_commit_with_stats(self, repo, sha: str) -> Optional[Dict[str, Any]]:
        try:
            url = f"https://api.github.com/repos/{repo.full_name}/commits/{sha}"
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                commit_data = response.json()
                stats = commit_data.get("stats", {})
                
                return {
                    "sha": sha,
                    "message": commit_data["commit"]["message"],
                    "author": {
                        "login": commit_data["author"]["login"] if commit_data["author"] else "unknown",
                        "name": commit_data["commit"]["author"]["name"],
                        "email": commit_data["commit"]["author"]["email"]
                    },
                    "timestamp": commit_data["commit"]["author"]["date"],
                    "repository": {
                        "id": repo.id,
                        "name": repo.name,
                        "full_name": repo.full_name,
                        "owner": repo.owner.login
                    },
                    "diff_stats": {
                        "additions": stats.get("additions", 0),
                        "deletions": stats.get("deletions", 0),
                        "changed_files": len(commit_data.get("files", []))
                    },
                    "url": commit_data["html_url"],
                    "parents": [p["sha"] for p in commit_data.get("parents", [])]
                }
        except Exception as e:
            print(f"Error fetching commit stats for {sha}: {e}")
            return None
    
    def _get_pr_with_stats(self, repo, pr_number: int) -> Optional[Dict[str, Any]]:
        try:
            url = f"https://api.github.com/repos/{repo.full_name}/pulls/{pr_number}"
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                pr_data = response.json()
                
                files_url = f"https://api.github.com/repos/{repo.full_name}/pulls/{pr_number}/files"
                files_response = requests.get(files_url, headers=self.headers)
                
                additions = deletions = changed_files = 0
                if files_response.status_code == 200:
                    files = files_response.json()
                    for file in files:
                        additions += file.get("additions", 0)
                        deletions += file.get("deletions", 0)
                        changed_files += 1
                
                return {
                    "id": pr_data["id"],
                    "number": pr_data["number"],
                    "title": pr_data["title"],
                    "state": pr_data["state"],
                    "author": {
                        "login": pr_data["user"]["login"],
                        "name": pr_data["user"]["name"]
                    },
                    "repository": {
                        "id": repo.id,
                        "name": repo.name,
                        "full_name": repo.full_name,
                        "owner": repo.owner.login
                    },
                    "created_at": pr_data["created_at"],
                    "updated_at": pr_data["updated_at"],
                    "closed_at": pr_data.get("closed_at"),
                    "merged_at": pr_data.get("merged_at"),
                    "draft": pr_data.get("draft", False),
                    "url": pr_data["html_url"],
                    "base_branch": pr_data["base"]["ref"],
                    "head_branch": pr_data["head"]["ref"],
                    "commits_count": pr_data["commits"],
                    "changed_files": changed_files,
                    "diff_stats": {
                        "additions": additions,
                        "deletions": deletions,
                        "changed_files": changed_files
                    }
                }
        except Exception as e:
            print(f"Error fetching PR stats for {pr_number}: {e}")
            return None
    
    def save_events_to_db(self, events: List[GitHubEvent]):
        with self.db.get_session() as session:
            for event in events:
                try:
                    if event.type == EventType.COMMIT:
                        self.db.save_commit(session, event.payload)
                    elif event.type == EventType.PULL_REQUEST:
                        self.db.save_pull_request(session, event.payload)
                except Exception as e:
                    print(f"Error saving event {event.id}: {e}")
    
    def generate_seed_data(self) -> List[GitHubEvent]:
        events = []
        now = datetime.now()
        
        for i in range(20):
            commit_date = now - timedelta(days=i, hours=i*2)
            
            event = GitHubEvent(
                id=f"seed_commit_{i}",
                type=EventType.COMMIT,
                timestamp=commit_date,
                repository=Repository(
                    id=12345,
                    name="test-repo",
                    full_name="test-org/test-repo",
                    owner="test-org"
                ),
                actor=Author(
                    login=f"developer_{i % 3}",
                    name=f"Developer {i % 3}",
                    email=f"dev{i % 3}@example.com"
                ),
                payload={
                    "sha": f"abc123def456_{i}",
                    "message": f"Feature implementation #{i}",
                    "author": {
                        "login": f"developer_{i % 3}",
                        "name": f"Developer {i % 3}",
                        "email": f"dev{i % 3}@example.com"
                    },
                    "timestamp": commit_date.isoformat(),
                    "repository": {
                        "id": 12345,
                        "name": "test-repo",
                        "full_name": "test-org/test-repo",
                        "owner": "test-org"
                    },
                    "diff_stats": {
                        "additions": 50 + (i * 10),
                        "deletions": 20 + (i * 5),
                        "changed_files": 2 + (i % 5)
                    },
                    "url": f"https://github.com/test-org/test-repo/commit/abc123def456_{i}",
                    "parents": []
                },
                raw_data={}
            )
            events.append(event)
        
        for i in range(10):
            pr_date = now - timedelta(days=i*2, hours=i*3)
            
            event = GitHubEvent(
                id=f"seed_pr_{i}",
                type=EventType.PULL_REQUEST,
                timestamp=pr_date,
                repository=Repository(
                    id=12345,
                    name="test-repo",
                    full_name="test-org/test-repo",
                    owner="test-org"
                ),
                actor=Author(
                    login=f"developer_{i % 3}",
                    name=f"Developer {i % 3}",
                    email=f"dev{i % 3}@example.com"
                ),
                payload={
                    "id": 54321 + i,
                    "number": i + 1,
                    "title": f"Add feature #{i}",
                    "state": "merged" if i % 2 == 0 else "open",
                    "author": {
                        "login": f"developer_{i % 3}",
                        "name": f"Developer {i % 3}"
                    },
                    "repository": {
                        "id": 12345,
                        "name": "test-repo",
                        "full_name": "test-org/test-repo",
                        "owner": "test-org"
                    },
                    "created_at": (pr_date - timedelta(days=1)).isoformat(),
                    "updated_at": pr_date.isoformat(),
                    "closed_at": pr_date.isoformat() if i % 2 == 0 else None,
                    "merged_at": pr_date.isoformat() if i % 2 == 0 else None,
                    "draft": False,
                    "url": f"https://github.com/test-org/test-repo/pull/{i+1}",
                    "base_branch": "main",
                    "head_branch": f"feature/branch-{i}",
                    "commits_count": 3 + (i % 5),
                    "changed_files": 5 + (i % 8),
                    "diff_stats": {
                        "additions": 100 + (i * 20),
                        "deletions": 30 + (i * 8),
                        "changed_files": 5 + (i % 8)
                    }
                },
                raw_data={}
            )
            events.append(event)
        
        return events
