"""
GitHub Integration Service
Handles webhooks from GitHub for automatic code review on push events
"""

import asyncio
import hmac
import hashlib
import tempfile
import shutil
import os
from typing import Dict, Optional
from pathlib import Path
import subprocess
import json


class GitHubIntegration:
    """
    Handles GitHub webhook events and triggers code analysis
    """
    
    def __init__(self, webhook_secret: Optional[str] = None):
        """
        Initialize GitHub integration
        
        Args:
            webhook_secret: Secret key for verifying GitHub webhooks (optional but recommended)
        """
        self.webhook_secret = webhook_secret or os.getenv("GITHUB_WEBHOOK_SECRET")
        self.temp_dir = tempfile.gettempdir()
    
    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify GitHub webhook signature
        
        Args:
            payload: Raw request body
            signature: X-Hub-Signature-256 header value
        
        Returns:
            True if signature is valid, False otherwise
        """
        if not self.webhook_secret:
            # If no secret configured, skip verification (not recommended for production)
            return True
        
        if not signature:
            return False
        
        # GitHub sends signature as "sha256=<hash>"
        expected_signature = 'sha256=' + hmac.new(
            self.webhook_secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, signature)
    
    async def handle_push_event(self, payload: Dict) -> Dict:
        """
        Handle GitHub push event
        
        Args:
            payload: GitHub webhook payload
        
        Returns:
            Analysis results
        """
        try:
            # Extract relevant information
            repo_name = payload.get('repository', {}).get('full_name')
            repo_url = payload.get('repository', {}).get('clone_url')
            branch = payload.get('ref', '').replace('refs/heads/', '')
            commits = payload.get('commits', [])
            pusher = payload.get('pusher', {}).get('name', 'unknown')
            
            if not repo_url or not branch:
                return {
                    "status": "error",
                    "message": "Invalid payload: missing repository or branch information"
                }
            
            print(f"\n{'='*60}")
            print(f"📥 GitHub Push Event Received")
            print(f"{'='*60}")
            print(f"Repository: {repo_name}")
            print(f"Branch: {branch}")
            print(f"Pusher: {pusher}")
            print(f"Commits: {len(commits)}")
            print(f"{'='*60}\n")
            
            # Clone the repository
            clone_path = await self.clone_repository(repo_url, branch)
            
            if not clone_path:
                return {
                    "status": "error",
                    "message": "Failed to clone repository"
                }
            
            try:
                # Get changed files from commits
                changed_files = self.extract_changed_files(commits)
                
                # Analyze changed files
                results = await self.analyze_repository(
                    clone_path,
                    changed_files,
                    repo_name,
                    branch
                )
                
                # Add metadata
                results['metadata'] = {
                    'repository': repo_name,
                    'branch': branch,
                    'pusher': pusher,
                    'commit_count': len(commits),
                    'changed_files': changed_files
                }
                
                return results
                
            finally:
                # Cleanup cloned repository
                self.cleanup_repository(clone_path)
        
        except Exception as e:
            print(f"❌ Error handling push event: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": "error",
                "message": str(e)
            }
    
    async def clone_repository(self, repo_url: str, branch: str) -> Optional[str]:
        """
        Clone GitHub repository to temporary directory
        
        Args:
            repo_url: Repository clone URL
            branch: Branch to clone
        
        Returns:
            Path to cloned repository or None if failed
        """
        try:
            # Create unique temp directory
            clone_dir = os.path.join(
                self.temp_dir,
                f"github_review_{os.urandom(8).hex()}"
            )
            
            print(f"🔄 Cloning repository...")
            print(f"   URL: {repo_url}")
            print(f"   Branch: {branch}")
            print(f"   Destination: {clone_dir}")
            
            # Clone repository with specific branch
            result = subprocess.run(
                [
                    'git', 'clone',
                    '--depth', '1',  # Shallow clone for speed
                    '--branch', branch,
                    repo_url,
                    clone_dir
                ],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                print(f"❌ Git clone failed: {result.stderr}")
                return None
            
            print(f"✅ Repository cloned successfully")
            return clone_dir
            
        except subprocess.TimeoutExpired:
            print("❌ Git clone timed out")
            return None
        except Exception as e:
            print(f"❌ Clone error: {e}")
            return None
    
    def extract_changed_files(self, commits: list) -> list:
        """
        Extract list of changed Python files from commits
        
        Args:
            commits: List of commit objects from GitHub payload
        
        Returns:
            List of changed Python file paths
        """
        changed_files = set()
        
        for commit in commits:
            # Get added, modified, and removed files
            for file in commit.get('added', []):
                if file.endswith('.py'):
                    changed_files.add(file)
            
            for file in commit.get('modified', []):
                if file.endswith('.py'):
                    changed_files.add(file)
        
        return list(changed_files)
    
    async def analyze_repository(
        self,
        repo_path: str,
        changed_files: list,
        repo_name: str,
        branch: str
    ) -> Dict:
        """
        Analyze repository using the code intelligence engines
        
        Args:
            repo_path: Path to cloned repository
            changed_files: List of files to analyze
            repo_name: Repository name
            branch: Branch name
        
        Returns:
            Analysis results
        """
        from engines.sast_engine import run_semgrep_analysis
        from engines.governance_engine import run_governance_check
        from engines.dast_engine import run_runtime_analysis
        
        print(f"\n{'='*60}")
        print(f"🔍 Starting Code Analysis")
        print(f"{'='*60}")
        
        # If no specific files changed, analyze all Python files
        if not changed_files:
            print("No specific files in commits, analyzing all Python files...")
            changed_files = []
            for root, dirs, files in os.walk(repo_path):
                # Skip .git and common ignore patterns
                dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', 'node_modules', 'venv', '.venv']]
                for file in files:
                    if file.endswith('.py'):
                        rel_path = os.path.relpath(os.path.join(root, file), repo_path)
                        changed_files.append(rel_path)
        
        print(f"Analyzing {len(changed_files)} Python files")
        
        results = {
            "repository": repo_name,
            "branch": branch,
            "files_analyzed": len(changed_files),
            "files": [],
            "summary": {
                "total_issues": 0,
                "critical_issues": 0,
                "high_issues": 0,
                "medium_issues": 0,
                "low_issues": 0
            }
        }
        
        # Analyze each file
        for file_rel_path in changed_files:
            file_path = os.path.join(repo_path, file_rel_path)
            
            if not os.path.exists(file_path):
                print(f"⚠️  File not found (may have been deleted): {file_rel_path}")
                continue
            
            print(f"\n📄 Analyzing: {file_rel_path}")
            
            try:
                # Run all three engines in parallel
                sast_task = asyncio.create_task(run_semgrep_analysis(file_path))
                governance_task = asyncio.create_task(run_governance_check(file_path))
                dast_task = asyncio.create_task(run_runtime_analysis(file_path))
                
                sast_results, governance_results, dast_results = await asyncio.gather(
                    sast_task, governance_task, dast_task
                )
                
                # Collect all findings
                all_findings = []
                all_findings.extend(sast_results.get('findings', []))
                all_findings.extend(governance_results.get('findings', []))
                all_findings.extend(dast_results.get('findings', []))
                
                # Count issues by severity
                file_summary = {
                    "critical": 0,
                    "high": 0,
                    "medium": 0,
                    "low": 0
                }
                
                for finding in all_findings:
                    severity = finding.get('severity', 'LOW').upper()
                    if severity == 'CRITICAL':
                        file_summary['critical'] += 1
                        results['summary']['critical_issues'] += 1
                    elif severity == 'HIGH':
                        file_summary['high'] += 1
                        results['summary']['high_issues'] += 1
                    elif severity == 'MEDIUM':
                        file_summary['medium'] += 1
                        results['summary']['medium_issues'] += 1
                    else:
                        file_summary['low'] += 1
                        results['summary']['low_issues'] += 1
                    
                    results['summary']['total_issues'] += 1
                
                results['files'].append({
                    "path": file_rel_path,
                    "status": "analyzed",
                    "findings_count": len(all_findings),
                    "summary": file_summary,
                    "engines": {
                        "sast": sast_results,
                        "governance": governance_results,
                        "dast": dast_results
                    }
                })
                
                # Print summary for this file
                if len(all_findings) > 0:
                    print(f"   ⚠️  Found {len(all_findings)} issue(s)")
                    print(f"   Critical: {file_summary['critical']}, High: {file_summary['high']}, Medium: {file_summary['medium']}, Low: {file_summary['low']}")
                else:
                    print(f"   ✅ No issues found")
                
            except Exception as e:
                print(f"   ❌ Analysis failed: {e}")
                results['files'].append({
                    "path": file_rel_path,
                    "status": "error",
                    "error": str(e)
                })
        
        # Calculate overall status
        if results['summary']['critical_issues'] > 0:
            results['status'] = 'critical'
            results['can_deploy'] = False
            results['message'] = f"⛔ Found {results['summary']['critical_issues']} critical issue(s). Deployment blocked."
        elif results['summary']['high_issues'] > 0:
            results['status'] = 'warning'
            results['can_deploy'] = False
            results['message'] = f"⚠️  Found {results['summary']['high_issues']} high severity issue(s). Review recommended."
        elif results['summary']['total_issues'] > 0:
            results['status'] = 'info'
            results['can_deploy'] = True
            results['message'] = f"ℹ️  Found {results['summary']['total_issues']} minor issue(s). Safe to deploy."
        else:
            results['status'] = 'success'
            results['can_deploy'] = True
            results['message'] = "✅ All checks passed. Safe to deploy!"
        
        print(f"\n{'='*60}")
        print(f"Analysis Complete: {results['message']}")
        print(f"{'='*60}\n")
        
        return results
    
    def cleanup_repository(self, repo_path: str):
        """
        Remove cloned repository
        
        Args:
            repo_path: Path to repository to remove
        """
        try:
            if os.path.exists(repo_path):
                print(f"🧹 Cleaning up: {repo_path}")
                shutil.rmtree(repo_path)
                print("✅ Cleanup complete")
        except Exception as e:
            print(f"⚠️  Cleanup warning: {e}")


# Global instance
github_integration = GitHubIntegration()