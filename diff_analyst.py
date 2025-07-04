from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import statistics
from models import *
from database import Database
import math


class DiffAnalyst:
    def __init__(self, db: Database):
        self.db = db
        self.churn_threshold_multiplier = 2.0
        self.risk_levels = {
            "low": 1.0,
            "medium": 2.0,
            "high": 3.0,
            "critical": 4.0
        }
    
    def analyze_code_churn(self, repository_id: int, period: MetricsPeriod, 
                          start_date: datetime, end_date: datetime) -> List[ChurnAlert]:
        alerts = []
        
        with self.db.get_session() as session:
            commits = session.query(self.db.DBCommit).filter(
                self.db.DBCommit.repository_id == repository_id,
                self.db.DBCommit.timestamp >= start_date,
                self.db.DBCommit.timestamp <= end_date
            ).all()
            
            author_churn = {}
            for commit in commits:
                author_id = commit.author_id
                if author_id not in author_churn:
                    author_churn[author_id] = {
                        "author": commit.author,
                        "total_additions": 0,
                        "total_deletions": 0,
                        "total_changes": 0,
                        "commit_count": 0
                    }
                
                author_churn[author_id]["total_additions"] += commit.additions
                author_churn[author_id]["total_deletions"] += commit.deletions
                author_churn[author_id]["total_changes"] += commit.additions + commit.deletions
                author_churn[author_id]["commit_count"] += 1
            
            for author_id, data in author_churn.items():
                current_churn = data["total_changes"]
                historical_avg = self._get_historical_average_churn(
                    session, author_id, repository_id, period, start_date
                )
                
                if historical_avg > 0:
                    churn_ratio = current_churn / historical_avg
                    is_spike = churn_ratio > self.churn_threshold_multiplier
                    
                    if is_spike:
                        risk_level = self._calculate_risk_level(churn_ratio)
                        
                        alert = ChurnAlert(
                            author=data["author"].login,
                            repository=f"repo_{repository_id}",
                            period=period,
                            churn_score=churn_ratio,
                            threshold=self.churn_threshold_multiplier,
                            is_spike=True,
                            previous_average=historical_avg,
                            current_period_churn=current_churn,
                            risk_level=risk_level
                        )
                        alerts.append(alert)
        
        return alerts
    
    def _get_historical_average_churn(self, session, author_id: int, repository_id: int, 
                                    period: MetricsPeriod, current_start: datetime) -> float:
        if period == MetricsPeriod.WEEKLY:
            lookback_periods = 4
            period_delta = timedelta(weeks=1)
        elif period == MetricsPeriod.MONTHLY:
            lookback_periods = 3
            period_delta = timedelta(days=30)
        else:
            lookback_periods = 7
            period_delta = timedelta(days=1)
        
        historical_churns = []
        
        for i in range(1, lookback_periods + 1):
            period_start = current_start - (period_delta * i)
            period_end = current_start - (period_delta * (i - 1))
            
            commits = session.query(self.db.DBCommit).filter(
                self.db.DBCommit.author_id == author_id,
                self.db.DBCommit.repository_id == repository_id,
                self.db.DBCommit.timestamp >= period_start,
                self.db.DBCommit.timestamp < period_end
            ).all()
            
            period_churn = sum(commit.additions + commit.deletions for commit in commits)
            if period_churn > 0:
                historical_churns.append(period_churn)
        
        return statistics.mean(historical_churns) if historical_churns else 0
    
    def _calculate_risk_level(self, churn_ratio: float) -> str:
        if churn_ratio >= 4.0:
            return "critical"
        elif churn_ratio >= 3.0:
            return "high"
        elif churn_ratio >= 2.0:
            return "medium"
        else:
            return "low"
    
    def calculate_dora_metrics(self, repository_id: int, period: MetricsPeriod,
                             start_date: datetime, end_date: datetime,
                             author_id: Optional[int] = None) -> DORAMetrics:
        
        with self.db.get_session() as session:
            commits_query = session.query(self.db.DBCommit).filter(
                self.db.DBCommit.repository_id == repository_id,
                self.db.DBCommit.timestamp >= start_date,
                self.db.DBCommit.timestamp <= end_date
            )
            
            prs_query = session.query(self.db.DBPullRequest).filter(
                self.db.DBPullRequest.repository_id == repository_id,
                self.db.DBPullRequest.created_at >= start_date,
                self.db.DBPullRequest.created_at <= end_date
            )
            
            ci_jobs_query = session.query(self.db.DBCIJob).filter(
                self.db.DBCIJob.repository_id == repository_id,
                self.db.DBCIJob.started_at >= start_date,
                self.db.DBCIJob.started_at <= end_date
            )
            
            if author_id:
                commits_query = commits_query.filter(self.db.DBCommit.author_id == author_id)
                prs_query = prs_query.filter(self.db.DBPullRequest.author_id == author_id)
            
            commits = commits_query.all()
            prs = prs_query.all()
            ci_jobs = ci_jobs_query.all()
            
            merged_prs = [pr for pr in prs if pr.merged_at is not None]
            failed_ci_jobs = [job for job in ci_jobs if job.conclusion == "failure"]
            
            lead_time = self._calculate_lead_time(merged_prs)
            deployment_frequency = self._calculate_deployment_frequency(merged_prs, period)
            change_failure_rate = self._calculate_change_failure_rate(ci_jobs, failed_ci_jobs)
            mttr = self._calculate_mean_time_to_recovery(failed_ci_jobs)
            
            review_time = self._calculate_review_time(session, prs)
            cycle_time = self._calculate_cycle_time(prs)
            
            total_additions = sum(commit.additions for commit in commits)
            total_deletions = sum(commit.deletions for commit in commits)
            total_files_changed = sum(commit.changed_files for commit in commits)
            
            churn_score = self._calculate_churn_score(commits, period)
            
            return DORAMetrics(
                period=period,
                start_date=start_date,
                end_date=end_date,
                repository=f"repo_{repository_id}",
                author=f"author_{author_id}" if author_id else None,
                lead_time_hours=lead_time,
                deployment_frequency=deployment_frequency,
                change_failure_rate=change_failure_rate,
                mean_time_to_recovery_hours=mttr,
                commits_count=len(commits),
                pull_requests_count=len(prs),
                merged_prs_count=len(merged_prs),
                review_time_hours=review_time,
                cycle_time_hours=cycle_time,
                ci_failures_count=len(failed_ci_jobs),
                total_additions=total_additions,
                total_deletions=total_deletions,
                total_files_changed=total_files_changed,
                churn_score=churn_score
            )
    
    def _calculate_lead_time(self, merged_prs: List) -> float:
        if not merged_prs:
            return 0.0
        
        lead_times = []
        for pr in merged_prs:
            if pr.created_at and pr.merged_at:
                lead_time = (pr.merged_at - pr.created_at).total_seconds() / 3600
                lead_times.append(lead_time)
        
        return statistics.mean(lead_times) if lead_times else 0.0
    
    def _calculate_deployment_frequency(self, merged_prs: List, period: MetricsPeriod) -> float:
        if not merged_prs:
            return 0.0
        
        if period == MetricsPeriod.DAILY:
            return len(merged_prs)
        elif period == MetricsPeriod.WEEKLY:
            return len(merged_prs) / 7
        elif period == MetricsPeriod.MONTHLY:
            return len(merged_prs) / 30
        
        return len(merged_prs)
    
    def _calculate_change_failure_rate(self, all_ci_jobs: List, failed_ci_jobs: List) -> float:
        if not all_ci_jobs:
            return 0.0
        
        return len(failed_ci_jobs) / len(all_ci_jobs)
    
    def _calculate_mean_time_to_recovery(self, failed_ci_jobs: List) -> float:
        if not failed_ci_jobs:
            return 0.0
        
        recovery_times = []
        for job in failed_ci_jobs:
            if job.started_at and job.completed_at:
                recovery_time = (job.completed_at - job.started_at).total_seconds() / 3600
                recovery_times.append(recovery_time)
        
        return statistics.mean(recovery_times) if recovery_times else 0.0
    
    def _calculate_review_time(self, session, prs: List) -> float:
        if not prs:
            return 0.0
        
        review_times = []
        for pr in prs:
            reviews = session.query(self.db.DBPullRequestReview).filter(
                self.db.DBPullRequestReview.pull_request_id == pr.id
            ).all()
            
            if reviews:
                first_review = min(reviews, key=lambda r: r.submitted_at)
                review_time = (first_review.submitted_at - pr.created_at).total_seconds() / 3600
                review_times.append(review_time)
        
        return statistics.mean(review_times) if review_times else 0.0
    
    def _calculate_cycle_time(self, prs: List) -> float:
        if not prs:
            return 0.0
        
        cycle_times = []
        for pr in prs:
            if pr.closed_at:
                cycle_time = (pr.closed_at - pr.created_at).total_seconds() / 3600
                cycle_times.append(cycle_time)
        
        return statistics.mean(cycle_times) if cycle_times else 0.0
    
    def _calculate_churn_score(self, commits: List, period: MetricsPeriod) -> float:
        if not commits:
            return 0.0
        
        total_churn = sum(commit.additions + commit.deletions for commit in commits)
        
        if period == MetricsPeriod.DAILY:
            return total_churn
        elif period == MetricsPeriod.WEEKLY:
            return total_churn / 7
        elif period == MetricsPeriod.MONTHLY:
            return total_churn / 30
        
        return total_churn
    
    def analyze_file_change_patterns(self, repository_id: int, start_date: datetime, 
                                   end_date: datetime) -> Dict[str, Any]:
        with self.db.get_session() as session:
            commits = session.query(self.db.DBCommit).filter(
                self.db.DBCommit.repository_id == repository_id,
                self.db.DBCommit.timestamp >= start_date,
                self.db.DBCommit.timestamp <= end_date
            ).all()
            
            file_change_frequency = {}
            author_file_changes = {}
            
            for commit in commits:
                author_login = commit.author.login
                files_changed = commit.changed_files
                
                if author_login not in author_file_changes:
                    author_file_changes[author_login] = 0
                author_file_changes[author_login] += files_changed
            
            hotspots = []
            for author, changes in author_file_changes.items():
                if changes > statistics.mean(list(author_file_changes.values())) * 2:
                    hotspots.append({
                        "author": author,
                        "file_changes": changes,
                        "risk_indicator": "high_churn"
                    })
            
            return {
                "analysis_period": f"{start_date.date()} to {end_date.date()}",
                "total_commits": len(commits),
                "author_file_changes": author_file_changes,
                "hotspots": hotspots,
                "average_files_per_commit": statistics.mean([c.changed_files for c in commits]) if commits else 0
            }
    
    def generate_risk_assessment(self, churn_alerts: List[ChurnAlert], 
                               dora_metrics: DORAMetrics) -> Dict[str, Any]:
        risk_factors = []
        overall_risk = "low"
        
        if churn_alerts:
            high_risk_alerts = [a for a in churn_alerts if a.risk_level in ["high", "critical"]]
            if high_risk_alerts:
                risk_factors.append(f"{len(high_risk_alerts)} high-risk churn alerts detected")
                overall_risk = "high"
        
        if dora_metrics.change_failure_rate > 0.15:
            risk_factors.append(f"High change failure rate: {dora_metrics.change_failure_rate:.2%}")
            overall_risk = "high"
        
        if dora_metrics.lead_time_hours > 168:
            risk_factors.append(f"Long lead time: {dora_metrics.lead_time_hours:.1f} hours")
            if overall_risk == "low":
                overall_risk = "medium"
        
        if dora_metrics.churn_score > 1000:
            risk_factors.append(f"High code churn: {dora_metrics.churn_score:.0f}")
            if overall_risk == "low":
                overall_risk = "medium"
        
        return {
            "overall_risk_level": overall_risk,
            "risk_factors": risk_factors,
            "total_alerts": len(churn_alerts),
            "recommendations": self._generate_risk_recommendations(risk_factors, overall_risk)
        }
    
    def _generate_risk_recommendations(self, risk_factors: List[str], overall_risk: str) -> List[str]:
        recommendations = []
        
        if overall_risk == "high":
            recommendations.append("Immediate attention required - schedule team review")
            recommendations.append("Consider implementing additional code review processes")
        
        if any("churn" in factor.lower() for factor in risk_factors):
            recommendations.append("Review recent large commits for potential issues")
            recommendations.append("Consider breaking down large features into smaller changes")
        
        if any("failure rate" in factor.lower() for factor in risk_factors):
            recommendations.append("Investigate CI/CD pipeline stability")
            recommendations.append("Add more comprehensive testing")
        
        if any("lead time" in factor.lower() for factor in risk_factors):
            recommendations.append("Streamline review process")
            recommendations.append("Consider parallel development workflows")
        
        return recommendations
