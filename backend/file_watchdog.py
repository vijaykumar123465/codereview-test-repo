import time
import asyncio
import aiohttp
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import os

class CodeFileHandler(FileSystemEventHandler):
    """
    Monitors file changes and triggers analysis
    """
    def __init__(self, watch_path, api_url="http://localhost:8000"):
        self.watch_path = watch_path
        self.api_url = api_url
        self.debounce_time = 2  # seconds
        self.last_trigger = {}
    
    def on_modified(self, event):
        """
        Called when a file is modified
        """
        if event.is_directory:
            return
        
        # Only watch Python files
        if not event.src_path.endswith('.py'):
            return
        
        # Debounce - avoid multiple triggers for same file
        current_time = time.time()
        if event.src_path in self.last_trigger:
            if current_time - self.last_trigger[event.src_path] < self.debounce_time:
                return
        
        self.last_trigger[event.src_path] = current_time
        
        print(f"\n{'='*60}")
        print(f"File modified: {event.src_path}")
        print(f"{'='*60}")
        
        # Trigger analysis
        asyncio.run(self.trigger_scan(event.src_path))
    
    async def trigger_scan(self, file_path):
        """
        Send scan request to backend and check for critical issues
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/scan",
                    json={"file_path": file_path}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        self.print_results(result)
                        
                        # Check for critical issues
                        await self.check_critical_issues(result, file_path, session)
                    else:
                        print(f"Error: HTTP {response.status}")
        except Exception as e:
            print(f"Error triggering scan: {e}")
    
    async def check_critical_issues(self, results, file_path, session):
        """
        Check if there are critical issues and alert via WebSocket
        """
        verdict = results.get("verdict", {})
        
        if verdict.get("severity") == "CRITICAL":
            # Count critical issues
            critical_count = 0
            critical_issues = []
            
            for engine_name, engine_data in results.get("engines", {}).items():
                for finding in engine_data.get("findings", []):
                    if finding.get("severity") == "CRITICAL":
                        critical_count += 1
                        critical_issues.append({
                            "engine": engine_name,
                            "rule": finding.get("rule", finding.get("issue")),
                            "line": finding.get("line"),
                            "message": finding.get("message", finding.get("details"))
                        })
            
            if critical_count > 0:
                print(f"\n{'='*60}")
                print(f"⚠️  CRITICAL ALERT: {critical_count} critical issues found!")
                print(f"{'='*60}\n")
                
                # Send alert to backend (will broadcast via WebSocket)
                try:
                    await session.post(
                        f"{self.api_url}/critical-alert",
                        json={
                            "file_path": file_path,
                            "critical_count": critical_count,
                            "issues": critical_issues
                        }
                    )
                except:
                    pass
    
    def print_results(self, results):
        """
        Pretty print scan results
        """
        print("\n" + "="*60)
        print("SCAN RESULTS")
        print("="*60)
        
        verdict = results.get("verdict", {})
        print(f"\nVERDICT: {verdict.get('decision', 'UNKNOWN')}")
        print(f"Severity: {verdict.get('severity', 'UNKNOWN')}")
        print(f"Reason: {verdict.get('reason', 'No reason provided')}")
        
        engines = results.get("engines", {})
        
        for engine_name, engine_data in engines.items():
            print(f"\n{engine_name.upper()} Engine:")
            print(f"  Status: {engine_data.get('status', 'unknown')}")
            
            findings = engine_data.get('findings', [])
            if findings:
                print(f"  Findings: {len(findings)}")
                for i, finding in enumerate(findings, 1):
                    print(f"\n  [{i}] {finding.get('rule', finding.get('issue', 'Unknown'))}")
                    print(f"      Line: {finding.get('line', 'N/A')}")
                    print(f"      {finding.get('message', finding.get('details', ''))}")
            else:
                print("  No issues found")
        
        print("\n" + "="*60 + "\n")

def start_monitoring(path=".", recursive=True):
    """
    Start monitoring the specified path
    """
    print(f"""
╔════════════════════════════════════════════════════════════╗
║     Hybrid Code Intelligence Agent - File Monitor         ║
╚════════════════════════════════════════════════════════════╝

Watching: {os.path.abspath(path)}
Recursive: {recursive}

Monitoring Python files for changes...
Press Ctrl+C to stop.
    """)
    
    event_handler = CodeFileHandler(path)
    observer = Observer()
    observer.schedule(event_handler, path, recursive=recursive)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nStopping file monitor...")
        observer.stop()
    
    observer.join()
    print("Monitor stopped.")

if __name__ == "__main__":
    import sys
    
    watch_path = sys.argv[1] if len(sys.argv) > 1 else "../test_files"
    start_monitoring(watch_path)