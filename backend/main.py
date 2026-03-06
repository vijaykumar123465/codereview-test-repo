from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import asyncio
import json
from pathlib import Path
from typing import List, Dict
import subprocess
import os
from datetime import datetime
import sqlite3
import tempfile
import shutil

app = FastAPI(title="Hybrid Code Intelligence Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database initialization
def init_db():
    conn = sqlite3.connect('projects.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            name TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            auto_scan INTEGER DEFAULT 0,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

from engines.sast_engine import run_semgrep_analysis
from engines.governance_engine import run_governance_check
from engines.dast_engine import run_runtime_analysis

# Import GitHub integration
import sys
sys.path.insert(0, '.')
from github_integration import github_integration

@app.get("/")
async def root():
    return {"status": "Hybrid Code Intelligence Agent Running"}

@app.get("/debug/path")
async def debug_path(path: str = "test_files/test_code.py"):
    """
    Debug endpoint to check path resolution
    """
    import sys
    
    info = {
        "input_path": path,
        "current_directory": os.getcwd(),
        "python_version": sys.version,
        "exists": os.path.exists(path),
        "is_file": os.path.isfile(path) if os.path.exists(path) else False,
        "absolute": os.path.abspath(path),
        "normalized": os.path.normpath(path),
        "directory_contents": []
    }
    
    # List current directory
    try:
        info["directory_contents"] = os.listdir(os.getcwd())[:20]  # First 20 items
    except:
        pass
    
    # Check test_files
    test_files_path = os.path.join(os.getcwd(), "test_files")
    if os.path.exists(test_files_path):
        try:
            info["test_files_contents"] = os.listdir(test_files_path)
        except:
            pass
    
    # Try one level up
    parent_dir = os.path.dirname(os.getcwd())
    test_files_parent = os.path.join(parent_dir, "test_files")
    if os.path.exists(test_files_parent):
        try:
            info["test_files_parent_contents"] = os.listdir(test_files_parent)
        except:
            pass
    
    return info

# Project Management Endpoints
@app.get("/projects")
async def get_projects():
    """Get all projects"""
    conn = sqlite3.connect('projects.db')
    c = conn.cursor()
    c.execute('SELECT name, path, auto_scan FROM projects')
    projects = [{"name": row[0], "path": row[1], "auto_scan": bool(row[2])} for row in c.fetchall()]
    conn.close()
    return {"projects": projects}

@app.get("/projects/{project_name}")
async def get_project(project_name: str):
    """Get specific project"""
    conn = sqlite3.connect('projects.db')
    c = conn.cursor()
    c.execute('SELECT name, path, auto_scan FROM projects WHERE name = ?', (project_name,))
    row = c.fetchone()
    conn.close()
    
    if row:
        return {"name": row[0], "path": row[1], "auto_scan": bool(row[2])}
    return JSONResponse(status_code=404, content={"error": "Project not found"})

@app.post("/projects")
async def create_project(request: dict):
    """Create new project"""
    name = request.get("name")
    path = request.get("path")
    create_dir = request.get("create_directory", False)
    
    if not name or not path:
        return JSONResponse(status_code=400, content={"error": "Name and path required"})
    
    # Create directory if requested
    if create_dir and not os.path.exists(path):
        try:
            os.makedirs(path)
        except Exception as e:
            return JSONResponse(status_code=400, content={"error": f"Failed to create directory: {str(e)}"})
    
    # Check if path exists
    if not os.path.exists(path):
        return JSONResponse(status_code=400, content={"error": f"Path does not exist: {path}"})
    
    conn = sqlite3.connect('projects.db')
    c = conn.cursor()
    try:
        c.execute('INSERT INTO projects (name, path, auto_scan, created_at) VALUES (?, ?, 0, ?)',
                  (name, path, datetime.now().isoformat()))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return JSONResponse(status_code=400, content={"error": "Project name already exists"})
    conn.close()
    
    return {"status": "success", "name": name, "path": path}

@app.put("/projects/{project_name}/settings")
async def update_project_settings(project_name: str, request: dict):
    """Update project settings"""
    auto_scan = request.get("auto_scan", False)
    
    conn = sqlite3.connect('projects.db')
    c = conn.cursor()
    c.execute('UPDATE projects SET auto_scan = ? WHERE name = ?', (int(auto_scan), project_name))
    conn.commit()
    conn.close()
    
    return {"status": "success"}

@app.delete("/projects/{project_name}")
async def delete_project(project_name: str):
    """Delete project from database (does not delete files)"""
    conn = sqlite3.connect('projects.db')
    c = conn.cursor()
    c.execute('DELETE FROM projects WHERE name = ?', (project_name,))
    conn.commit()
    conn.close()
    
    return {"status": "success"}

@app.post("/deploy/scan")
async def deploy_scan(request: dict):
    """
    Scan entire project for production deployment
    Includes cross-file context analysis
    """
    project_name = request.get("project_name")
    project_path = request.get("project_path")
    
    if not project_path or not os.path.exists(project_path):
        return JSONResponse(status_code=404, content={"error": "Project path not found"})
    
    print(f"\n{'='*60}")
    print(f"Starting deployment scan for: {project_name}")
    print(f"Path: {project_path}")
    print(f"{'='*60}\n")
    
    # Scan all Python files
    python_files = []
    for root, dirs, files in os.walk(project_path):
        # Skip common directories
        dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', 'node_modules', 'venv', '.venv']]
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    
    print(f"Found {len(python_files)} Python files")
    
    # Build project context (imports map)
    project_context = build_project_context(python_files)
    
    # Scan each file
    results = []
    critical_count = 0
    warning_count = 0
    clean_count = 0
    
    for file_path in python_files:
        print(f"Scanning: {file_path}")
        
        # Get file context (imported files)
        file_context = get_file_context(file_path, project_context)
        
        # Run analysis with context
        file_result = await scan_file_with_context(file_path, file_context)
        
        has_critical = any(f.get('severity') == 'CRITICAL' for f in file_result.get('findings', []))
        has_warnings = any(f.get('severity') in ['HIGH', 'MEDIUM'] for f in file_result.get('findings', []))
        
        if has_critical:
            critical_count += 1
        elif has_warnings:
            warning_count += 1
        else:
            clean_count += 1
        
        results.append({
            "filename": os.path.basename(file_path),
            "path": file_path,
            "has_critical": has_critical,
            "has_warnings": has_warnings,
            "issues": len(file_result.get('findings', []))
        })
    
    can_deploy = critical_count == 0
    
    print(f"\n{'='*60}")
    print(f"Scan complete:")
    print(f"  Total files: {len(python_files)}")
    print(f"  Clean: {clean_count}")
    print(f"  Warnings: {warning_count}")
    print(f"  Critical: {critical_count}")
    print(f"  Can deploy: {can_deploy}")
    print(f"{'='*60}\n")
    
    return {
        "can_deploy": can_deploy,
        "total_files": len(python_files),
        "clean_files": clean_count,
        "critical_count": critical_count,
        "warning_count": warning_count,
        "files": results
    }

def build_project_context(python_files: List[str]) -> Dict:
    """
    Build a map of imports across the project
    """
    context = {}
    
    for file_path in python_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            imports = []
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('import ') or line.startswith('from '):
                    imports.append(line)
            
            context[file_path] = {
                "imports": imports,
                "content": content
            }
        except:
            pass
    
    return context

def get_file_context(file_path: str, project_context: Dict) -> str:
    """
    Get context for a specific file (its imports)
    """
    file_info = project_context.get(file_path, {})
    imports = file_info.get("imports", [])
    
    context_info = f"File: {os.path.basename(file_path)}\n"
    context_info += f"Imports: {', '.join(imports) if imports else 'None'}\n"
    
    return context_info

async def scan_file_with_context(file_path: str, context: str):
    """
    Scan a file with cross-file context
    """
    try:
        # Run governance check with context
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
        
        from engines.governance_engine import run_governance_check_with_context
        
        # Use context-aware scanning if available
        try:
            result = await run_governance_check_with_context(file_path, context)
        except:
            # Fallback to regular scan
            from engines.governance_engine import run_governance_check
            result = await run_governance_check(file_path)
        
        return result
    except Exception as e:
        print(f"Error scanning {file_path}: {e}")
        return {"findings": []}

@app.post("/deploy/confirm")
async def confirm_deployment(request: dict):
    """
    Confirm deployment to production
    """
    project_name = request.get("project_name")
    
    print(f"🚀 Deploying {project_name} to production")
    
    # Here you would integrate with actual deployment systems
    # For now, just simulate success
    
    return {
        "status": "success",
        "message": f"Project {project_name} deployed successfully"
    }
@app.post("/scan")
async def scan_code(request: dict):
    """
    Endpoint to trigger code scan - ALWAYS reads fresh file content
    """
    file_path = request.get("file_path", "test_code.py")
    
    # Normalize path - remove leading slashes, handle both absolute and relative
    if file_path.startswith('/'):
        file_path = file_path[1:]
    
    # Try multiple path variations
    possible_paths = [
        file_path,
        os.path.join("test_files", os.path.basename(file_path)),
        os.path.join("..", file_path),
        os.path.abspath(file_path)
    ]
    
    actual_path = None
    for path in possible_paths:
        if os.path.exists(path):
            actual_path = path
            break
    
    if not actual_path:
        return JSONResponse(
            status_code=404,
            content={
                "error": f"File not found: {file_path}",
                "tried_paths": possible_paths
            }
        )
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "file": actual_path,
        "engines": {}
    }
    
    # Run parallel analysis - each engine reads file fresh
    sast_task = asyncio.create_task(run_semgrep_analysis(actual_path))
    governance_task = asyncio.create_task(run_governance_check(actual_path))
    dast_task = asyncio.create_task(run_runtime_analysis(actual_path))
    
    sast_results, governance_results, dast_results = await asyncio.gather(
        sast_task, governance_task, dast_task
    )
    
    results["engines"]["sast"] = sast_results
    results["engines"]["governance"] = governance_results
    results["engines"]["dast"] = dast_results
    
    # Calculate verdict
    verdict = calculate_verdict(results)
    results["verdict"] = verdict
    
    # Broadcast to WebSocket clients
    await manager.broadcast({
        "type": "scan_complete",
        "data": results
    })
    
    return JSONResponse(content=results)

@app.post("/github/webhook")
async def github_webhook(request: dict):
    """
    GitHub webhook endpoint
    Receives push events from GitHub and triggers code analysis
    
    Setup instructions:
    1. Go to your GitHub repository Settings > Webhooks
    2. Add webhook with URL: http://your-server:8000/github/webhook
    3. Content type: application/json
    4. Secret: (optional but recommended - set GITHUB_WEBHOOK_SECRET env var)
    5. Events: Just the push event
    """
    try:
        # Verify this is a push event
        event_type = request.get('ref', '').startswith('refs/heads/')
        
        if not event_type:
            return JSONResponse(
                status_code=400,
                content={"error": "Only push events are supported"}
            )
        
        print(f"\n{'='*60}")
        print("📥 Received GitHub Webhook")
        print(f"{'='*60}")
        
        # Handle push event
        results = await github_integration.handle_push_event(request)
        
        # Broadcast results to WebSocket clients
        await manager.broadcast({
            "type": "github_analysis_complete",
            "data": results
        })
        
        return JSONResponse(content=results)
        
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@app.post("/github/verify")
async def verify_github_signature(request: dict, signature: str = ""):
    """
    Test endpoint to verify GitHub webhook signature
    """
    try:
        payload = json.dumps(request).encode('utf-8')
        is_valid = github_integration.verify_signature(payload, signature)
        
        return {
            "valid": is_valid,
            "message": "Signature is valid" if is_valid else "Invalid signature"
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@app.get("/github/status")
async def github_status():
    """
    Check GitHub integration status
    """
    has_secret = github_integration.webhook_secret is not None
    
    # Test if git is available
    git_available = False
    try:
        result = subprocess.run(['git', '--version'], capture_output=True, timeout=5)
        git_available = result.returncode == 0
    except:
        pass
    
    return {
        "configured": True,
        "webhook_secret_set": has_secret,
        "git_available": git_available,
        "webhook_url": "/github/webhook",
        "setup_instructions": {
            "step_1": "Go to your GitHub repository Settings > Webhooks",
            "step_2": "Click 'Add webhook'",
            "step_3": "Set Payload URL to: http://your-server:8000/github/webhook",
            "step_4": "Set Content type to: application/json",
            "step_5": "Set Secret to your GITHUB_WEBHOOK_SECRET (optional but recommended)",
            "step_6": "Select 'Just the push event'",
            "step_7": "Click 'Add webhook'"
        }
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"status": "received", "data": data})
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/add-suggestion-comment")
async def add_suggestion_comment(request: dict):
    """
    Add AI suggestion as comment above the line
    """
    file_path = request.get("file_path")
    line_num = request.get("line")
    suggestion = request.get("suggestion")
    
    # Normalize path
    if file_path.startswith('/'):
        file_path = file_path[1:]
    
    possible_paths = [
        file_path,
        os.path.join("test_files", os.path.basename(file_path)),
        os.path.join("..", file_path)
    ]
    
    actual_path = None
    for path in possible_paths:
        if os.path.exists(path):
            actual_path = path
            break
    
    if not actual_path:
        return {"status": "error", "message": f"File not found: {file_path}"}
    
    try:
        # Read file with proper encoding
        with open(actual_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if 0 < line_num <= len(lines):
            # Get indentation from the target line
            target_line = lines[line_num - 1]
            indent = len(target_line) - len(target_line.lstrip())
            
            # Create comment with same indentation
            comment = ' ' * indent + f"# AI Suggestion: {suggestion}\n"
            
            # Insert comment above the line
            lines.insert(line_num - 1, comment)
            
            # Write back to file
            with open(actual_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            
            print(f"✅ Added suggestion comment to {actual_path} at line {line_num}")
            
            return {
                "status": "success", 
                "message": f"Suggestion added at line {line_num}",
                "file": actual_path
            }
        else:
            return {"status": "error", "message": f"Line {line_num} out of range (file has {len(lines)} lines)"}
    except Exception as e:
        print(f"❌ Error adding suggestion: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/apply-fix")
async def apply_fix(request: dict):
    """
    Apply auto-remediation to code - supports both single line and batch fixes
    """
    file_path = request.get("file_path")
    
    if "line" in request and "new_code" in request:
        return await apply_single_line_fix(file_path, request)
    else:
        return await apply_batch_fixes(file_path, request.get("fixes", []))

async def apply_single_line_fix(file_path: str, fix_data: dict):
    """
    Apply a single line fix by replacing exact line
    """
    line_num = fix_data.get("line")
    new_code = fix_data.get("new_code", "")
    
    # Normalize path
    if file_path.startswith('/'):
        file_path = file_path[1:]
    
    possible_paths = [
        file_path,
        os.path.join("test_files", os.path.basename(file_path)),
        os.path.join("..", file_path)
    ]
    
    actual_path = None
    for path in possible_paths:
        if os.path.exists(path):
            actual_path = path
            break
    
    if not actual_path:
        return {"status": "error", "message": f"File not found: {file_path}"}
    
    try:
        # Read file with proper encoding
        with open(actual_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if 0 < line_num <= len(lines):
            # Get original line for indentation
            original_line = lines[line_num - 1]
            indent = len(original_line) - len(original_line.lstrip())
            
            # Apply new code with proper indentation
            if new_code.strip():
                # Add indentation and newline
                fixed_line = ' ' * indent + new_code.strip() + '\n'
                lines[line_num - 1] = fixed_line
                
                # Write back to file
                with open(actual_path, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
                
                print(f"✅ Applied fix to {actual_path} at line {line_num}")
                print(f"   Old: {original_line.strip()}")
                print(f"   New: {fixed_line.strip()}")
                
                return {
                    "status": "success",
                    "message": f"Applied fix to line {line_num}",
                    "line": line_num,
                    "file": actual_path
                }
            else:
                return {"status": "error", "message": "New code is empty"}
        else:
            return {
                "status": "error", 
                "message": f"Line {line_num} out of range (file has {len(lines)} lines)"
            }
            
    except Exception as e:
        print(f"❌ Error applying fix: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

async def apply_batch_fixes(file_path: str, fixes: list):
    """
    Apply multiple fixes as TODO comments
    """
    try:
        with open(file_path, 'r') as f:
            lines = f.readlines()
        
        applied_count = 0
        for fix in fixes:
            if fix.get("suggestion") and fix.get("line"):
                line_num = fix.get("line") - 1
                if 0 <= line_num < len(lines):
                    suggestion = fix.get("suggestion")
                    lines[line_num] = f"# TODO: {suggestion}\n{lines[line_num]}"
                    applied_count += 1
        
        with open(file_path, 'w') as f:
            f.writelines(lines)
        
        return {
            "status": "success", 
            "message": f"Applied {applied_count} fix suggestions",
            "fixes_applied": applied_count
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/critical-alert")
async def critical_alert(request: dict):
    """
    Notify frontend of critical issues found during auto-scan
    """
    await manager.broadcast({
        "type": "critical_alert",
        "data": request
    })
    return {"status": "broadcast"}

def calculate_verdict(results: dict) -> dict:
    """
    Calculate overall verdict based on engine results
    """
    critical_count = 0
    high_count = 0
    
    for engine_name, engine_data in results["engines"].items():
        if engine_data.get("status") == "error":
            critical_count += 1
        elif engine_data.get("status") == "warning":
            high_count += 1
    
    if critical_count > 0:
        return {
            "decision": "BLOCK",
            "severity": "CRITICAL",
            "reason": f"Found {critical_count} critical issues"
        }
    elif high_count > 0:
        return {
            "decision": "WARN",
            "severity": "HIGH",
            "reason": f"Found {high_count} high-priority warnings"
        }
    else:
        return {
            "decision": "APPROVE",
            "severity": "NONE",
            "reason": "All checks passed"
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)