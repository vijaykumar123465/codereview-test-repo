import asyncio
import json
import os
from typing import Dict, List
import aiohttp

# Ollama configuration
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5-coder:7b"  # Recommended for code analysis

async def run_governance_check(file_path: str) -> Dict:
    """
    Run LLM-powered governance check - ALWAYS reads fresh file
    """
    try:
        # CRITICAL: Read fresh file content every time
        with open(file_path, 'r') as f:
            code_content = f.read()
        
        guidelines = read_guidelines()
        findings = await analyze_with_ollama(code_content, guidelines, file_path)
        
        # Categorize each finding
        for finding in findings:
            categorize_fix(finding, code_content)
        
        return {
            "status": "error" if findings else "success",
            "findings": findings,
            "engine": "governance-llm"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "findings": [],
            "error": str(e),
            "engine": "governance"
        }

async def run_governance_check_with_context(file_path: str, context: str) -> Dict:
    """
    Run governance check with cross-file context awareness
    """
    try:
        with open(file_path, 'r') as f:
            code_content = f.read()
        
        guidelines = read_guidelines()
        findings = await analyze_with_context(code_content, guidelines, context)
        
        for finding in findings:
            categorize_fix(finding, code_content)
        
        return {
            "status": "error" if findings else "success",
            "findings": findings,
            "engine": "governance-llm-context"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "findings": [],
            "error": str(e),
            "engine": "governance"
        }

async def analyze_with_context(code: str, guidelines: str, context: str) -> List[Dict]:
    """
    Analyze code with cross-file context using Ollama
    """
    try:
        prompt = f"""You are an expert code governance AI with cross-file context awareness.

CONTEXT INFORMATION:
{context}

GUIDELINES:
{guidelines}

CODE TO ANALYZE:
```python
{code}
```

Use the context to understand:
- What classes/methods are imported
- Whether imported items exist and their signatures
- Cross-file dependencies

Only flag REAL issues with actual code snippets.

Response format (JSON array):
[
  {{
    "rule": "Issue type",
    "line": 10,
    "severity": "CRITICAL",
    "message": "Description",
    "suggestion": "How to fix",
    "oldCode": "actual code line",
    "newCode": "fixed code"
  }}
]"""

        response_text = await call_ollama(prompt)
        
        # Parse JSON from response
        response_text = extract_json(response_text)
        findings = json.loads(response_text)
        
        for finding in findings:
            finding['canAutoFix'] = True
            if not finding.get('oldCode') or len(finding.get('oldCode', '')) > 200:
                line_num = finding.get('line', 1)
                lines = code.split('\n')
                if 0 < line_num <= len(lines):
                    finding['oldCode'] = lines[line_num - 1].strip()
        
        return findings if isinstance(findings, list) else []
        
    except Exception as e:
        print(f"Context analysis error: {e}")
        return simulate_governance_check(code, guidelines)

def read_guidelines() -> str:
    """
    Read organizational guidelines
    """
    default_guidelines = """
# Organizational Code Guidelines

## Financial Policies
1. Never hardcode discount rates, prices, or financial calculations
2. All financial constants must be retrieved from ConfigService
3. Discount rates must support A/B testing and regional variations

## Security Policies
1. All user input must be sanitized before database operations
2. No hardcoded credentials or API keys
3. Sensitive data must be encrypted at rest

## Performance Policies
1. Database queries must use connection pooling
2. Large datasets must be paginated
3. Memory-intensive operations must have cleanup handlers

## Code Quality
1. All public APIs must have OpenAPI documentation
2. Error messages must not expose internal details
3. Logging must follow structured format
"""
    
    guidelines_path = "guidelines.md"
    
    try:
        if os.path.exists(guidelines_path):
            with open(guidelines_path, 'r') as f:
                return f.read()
    except:
        pass
    
    return default_guidelines

def categorize_fix(finding: dict, code_content: str):
    """
    ALL issues should be auto-fixable - system reads guidelines for context
    """
    # Everything is auto-fixable if we have a newCode suggestion
    if finding.get('newCode'):
        finding['canAutoFix'] = True
    else:
        # If no newCode provided, still mark as fixable but note it
        finding['canAutoFix'] = True
        if not finding.get('suggestion'):
            finding['suggestion'] = 'Review code and apply recommended changes'

async def call_ollama(prompt: str, system_prompt: str = "Respond only with valid JSON. Always provide exact code snippets, never descriptions.") -> str:
    """
    Call Ollama API for LLM inference
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "system": system_prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "top_p": 0.9,
                        "num_predict": 4000
                    }
                },
                timeout=aiohttp.ClientTimeout(total=120)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get("response", "")
                else:
                    error_text = await response.text()
                    raise Exception(f"Ollama API error: {response.status} - {error_text}")
    except Exception as e:
        print(f"Ollama API call failed: {e}")
        raise

def extract_json(text: str) -> str:
    """
    Extract JSON from response text (handles markdown code blocks)
    """
    text = text.strip()
    
    # Remove markdown code blocks
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    
    # Find JSON array or object
    if text.startswith('['):
        end = text.rfind(']')
        if end != -1:
            text = text[:end+1]
    elif text.startswith('{'):
        end = text.rfind('}')
        if end != -1:
            text = text[:end+1]
    
    return text

async def analyze_with_ollama(code: str, guidelines: str, file_path: str) -> List[Dict]:
    """
    Use Ollama local LLM - provide actual code snippets, not descriptions
    """
    try:
        requirements = ""
        req_path = "requirements_spec.md"
        if os.path.exists(req_path):
            with open(req_path, 'r') as f:
                requirements = f.read()
        
        prompt = f"""You are an expert code governance AI. Analyze code and provide fixes with ACTUAL CODE SNIPPETS.

CRITICAL RULES:
1. oldCode: MUST be the EXACT code line from the file (not a description)
2. newCode: MUST be the EXACT replacement code (not a description)
3. suggestion: Human-readable explanation (this is separate)
4. Do NOT detect os.getenv(), ConfigService.get(), or SecureVault as hardcoded
5. Only flag ACTUAL hardcoded values like "password123" or 0.20

GUIDELINES:
{guidelines}

CODE:
```python
{code}
```

Response format (JSON array):
[
  {{
    "rule": "Hardcoded Credentials",
    "line": 10,
    "severity": "CRITICAL",
    "message": "Password hardcoded instead of using environment variable",
    "suggestion": "Use os.getenv() to retrieve password from environment",
    "oldCode": "DATABASE_PASSWORD = \\"super_secret_123\\"",
    "newCode": "DATABASE_PASSWORD = os.getenv(\\"DATABASE_PASSWORD\\")"
  }}
]

WRONG (do not do this):
- oldCode: "Credentials hardcoded in source code" ❌
- newCode: "Use environment variables" ❌

CORRECT:
- oldCode: "API_KEY = \\"sk-12345\\"" ✅
- newCode: "API_KEY = os.getenv(\\"API_KEY\\")" ✅

DO NOT FLAG THESE AS ISSUES:
- os.getenv("PASSWORD") ← Already safe ✅
- ConfigService.get() ← Already safe ✅
- SecureVault.get() ← Already safe ✅

Only return issues for ACTUAL problems in the code."""

        response_text = await call_ollama(prompt)
        response_text = extract_json(response_text)
        
        findings = json.loads(response_text)
        
        for finding in findings:
            finding['canAutoFix'] = True
            # Ensure we have oldCode and newCode, not descriptions
            if not finding.get('oldCode') or len(finding.get('oldCode', '')) > 200:
                # Fallback: extract from file
                line_num = finding.get('line', 1)
                lines = code.split('\n')
                if 0 < line_num <= len(lines):
                    finding['oldCode'] = lines[line_num - 1].strip()
        
        return findings if isinstance(findings, list) else []
        
    except Exception as e:
        print(f"Ollama analysis error: {e}")
        return simulate_governance_check(code, guidelines)

def simulate_governance_check(code: str, guidelines: str) -> List[Dict]:
    """
    Simulate governance check - detect REAL issues only
    """
    findings = []
    lines = code.split('\n')
    
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        
        # Skip empty lines and comments
        if not line_stripped or line_stripped.startswith('#'):
            continue
        
        # Hardcoded credentials - but NOT if using os.getenv, SecureVault, etc.
        if any(kw in line.lower() for kw in ['password', 'api_key', 'secret', 'token']) and '=' in line:
            # Check if it's actually hardcoded (has quotes with value)
            if ('"' in line or "'" in line) and not any(safe in line for safe in ['getenv', 'SecureVault', 'config.get', 'os.environ']):
                # Extract the actual assignment
                if '=' in line:
                    var_name = line.split('=')[0].strip()
                    old_value = line.split('=')[1].strip()
                    findings.append({
                        "rule": "Hardcoded Credentials",
                        "line": i + 1,
                        "severity": "CRITICAL",
                        "message": "Credentials hardcoded in source code",
                        "suggestion": "Use environment variables or secure vault for credentials",
                        "oldCode": line_stripped,
                        "newCode": f"{var_name} = os.getenv('{var_name}')",
                        "canAutoFix": True
                    })
        
        # Hardcoded discount/price - but NOT if using ConfigService
        elif any(kw in line.lower() for kw in ['discount', 'price', 'rate']) and '=' in line:
            if any(char.isdigit() for char in line) and '0.' in line and 'ConfigService' not in line:
                var_name = line.split('=')[0].strip()
                findings.append({
                    "rule": "Hardcoded Configuration",
                    "line": i + 1,
                    "severity": "HIGH",
                    "message": "Financial constant hardcoded - violates policy",
                    "suggestion": "Use ConfigService to retrieve dynamic values",
                    "oldCode": line_stripped,
                    "newCode": f"{var_name} = ConfigService.get('{var_name.lower()}')",
                    "canAutoFix": True
                })
        
        # SQL injection - string formatting in queries
        elif ('execute' in line.lower() or 'query' in line.lower()):
            if ('f"' in line or "f'" in line or '+' in line) and ('SELECT' in line or 'INSERT' in line or 'UPDATE' in line or 'DELETE' in line):
                findings.append({
                    "rule": "SQL Injection",
                    "line": i + 1,
                    "severity": "CRITICAL",
                    "message": "SQL query vulnerable to injection",
                    "suggestion": "Use parameterized queries instead of string formatting",
                    "oldCode": line_stripped,
                    "newCode": 'cursor.execute("SELECT * FROM table WHERE id = ?", (user_input,))',
                    "canAutoFix": True
                })
        
        # Division without zero check
        elif '/' in line and '//' not in line and '/*' not in line:
            if '=' in line and not any(check in line for check in ['if', '!= 0', '> 0']):
                var_name = line.split('=')[0].strip()
                expr = line.split('=')[1].strip()
                # Extract divisor
                parts = expr.split('/')
                if len(parts) == 2:
                    divisor = parts[1].strip()
                    findings.append({
                        "rule": "Division by Zero Risk",
                        "line": i + 1,
                        "severity": "HIGH",
                        "message": "Potential division by zero - add safety check",
                        "suggestion": "Add validation to prevent division by zero",
                        "oldCode": line_stripped,
                        "newCode": f"{var_name} = {expr} if {divisor} != 0 else 0",
                        "canAutoFix": True
                    })
    
    return findings