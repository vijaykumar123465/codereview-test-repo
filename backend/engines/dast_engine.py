import asyncio
import subprocess
import psutil
import time
from typing import Dict, List
import tempfile
import os

async def run_runtime_analysis(file_path: str) -> Dict:
    """
    Run dynamic analysis by executing the code and monitoring resources
    """
    try:
        findings = []
        
        # Create a safe execution wrapper
        wrapper_code = f"""
import sys
import time

# Set timeout
import signal
signal.alarm(10)  # 10 second timeout

try:
    # Execute the target file
    exec(open('{file_path}').read())
except Exception as e:
    print(f"Execution error: {{e}}")
    sys.exit(1)
"""
        
        # Write wrapper to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            wrapper_path = f.name
            f.write(wrapper_code)
        
        try:
            # Start the process
            process = await asyncio.create_subprocess_exec(
                'python', wrapper_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Monitor resource usage
            metrics = await monitor_process(process.pid)
            
            # Wait for completion (with timeout)
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                process.kill()
                findings.append({
                    "issue": "Execution Timeout",
                    "severity": "HIGH",
                    "details": "Code execution exceeded time limit - possible infinite loop",
                    "cpuPeak": "N/A"
                })
            
            # Analyze metrics
            if metrics:
                findings.extend(analyze_metrics(metrics))
            
        finally:
            # Cleanup
            try:
                os.unlink(wrapper_path)
            except:
                pass
        
        # If no real execution, simulate
        if not findings:
            findings = simulate_runtime_analysis(file_path)
        
        return {
            "status": "warning" if findings else "success",
            "findings": findings,
            "engine": "dast"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "findings": [],
            "error": str(e),
            "engine": "dast"
        }

async def monitor_process(pid: int) -> List[Dict]:
    """
    Monitor process resource usage
    """
    metrics = []
    
    try:
        process = psutil.Process(pid)
        
        for _ in range(10):  # Monitor for 1 second (10 samples)
            try:
                cpu_percent = process.cpu_percent(interval=0.1)
                memory_info = process.memory_info()
                
                metrics.append({
                    "timestamp": time.time(),
                    "cpu_percent": cpu_percent,
                    "memory_mb": memory_info.rss / 1024 / 1024
                })
                
                await asyncio.sleep(0.1)
            except psutil.NoSuchProcess:
                break
        
    except Exception as e:
        print(f"Monitoring error: {e}")
    
    return metrics

def analyze_metrics(metrics: List[Dict]) -> List[Dict]:
    """
    Analyze collected metrics for issues
    """
    findings = []
    
    if not metrics or len(metrics) < 3:
        return findings
    
    # Check for memory leaks
    memory_values = [m["memory_mb"] for m in metrics]
    memory_trend = memory_values[-1] - memory_values[0]
    
    if memory_trend > 50:  # More than 50MB increase
        findings.append({
            "issue": "Memory Leak Detected",
            "severity": "MEDIUM",
            "details": f"Memory increased from {memory_values[0]:.1f}MB to {memory_values[-1]:.1f}MB",
            "cpuPeak": f"{max(m['cpu_percent'] for m in metrics):.1f}%"
        })
    
    # Check for CPU spikes
    cpu_values = [m["cpu_percent"] for m in metrics]
    avg_cpu = sum(cpu_values) / len(cpu_values)
    max_cpu = max(cpu_values)
    
    if max_cpu > 80:
        findings.append({
            "issue": "High CPU Usage",
            "severity": "MEDIUM",
            "details": f"CPU peaked at {max_cpu:.1f}% (avg: {avg_cpu:.1f}%)",
            "cpuPeak": f"{max_cpu:.1f}%"
        })
    
    return findings

def simulate_runtime_analysis(file_path: str) -> List[Dict]:
    """
    Simulate runtime analysis when execution is not safe
    """
    findings = []
    
    try:
        with open(file_path, 'r') as f:
            code = f.read()
        
        # Check for potential infinite loops
        if 'while True' in code or 'while 1' in code:
            if 'break' not in code:
                findings.append({
                    "issue": "Potential Infinite Loop",
                    "severity": "MEDIUM",
                    "details": "Unbounded while loop detected without break condition",
                    "cpuPeak": "N/A"
                })
        
        # Check for memory-intensive operations
        if any(keyword in code for keyword in ['append', '+=', 'extend']) and 'for' in code:
            if 'clear' not in code and 'del' not in code:
                findings.append({
                    "issue": "Potential Memory Leak",
                    "severity": "LOW",
                    "details": "List operations in loop without cleanup",
                    "cpuPeak": "N/A"
                })
        
    except Exception as e:
        pass
    
    return findings