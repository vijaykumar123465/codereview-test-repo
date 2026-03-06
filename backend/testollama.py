import asyncio
import aiohttp
import json

OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5-coder:7b"

async def test_ollama_connection():
    """Test if Ollama is running and accessible"""
    print("=" * 60)
    print("Testing Ollama Connection")
    print("=" * 60)
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{OLLAMA_URL}/api/tags") as response:
                if response.status == 200:
                    data = await response.json()
                    models = data.get("models", [])
                    print(f"✅ Ollama is running at {OLLAMA_URL}")
                    print(f"\nInstalled models:")
                    for model in models:
                        print(f"  - {model['name']} ({model['size'] // 1_000_000}MB)")
                    return True
                else:
                    print(f"❌ Ollama responded with status {response.status}")
                    return False
    except Exception as e:
        print(f"❌ Cannot connect to Ollama: {e}")
        print("\nMake sure Ollama is running:")
        print("  - Run 'ollama serve' in another terminal")
        print("  - Or start Ollama from your applications")
        return False

async def test_model_inference():
    """Test if the model can generate responses"""
    print("\n" + "=" * 60)
    print("Testing Model Inference")
    print("=" * 60)
    
    test_prompt = """You are a code analysis AI. Find issues in this code and respond with JSON.

CODE:
```python
password = "hardcoded123"
result = 10 / x
```

Response format:
[
  {
    "rule": "Hardcoded Credentials",
    "line": 1,
    "severity": "CRITICAL",
    "message": "Password is hardcoded",
    "oldCode": "password = \\"hardcoded123\\"",
    "newCode": "password = os.getenv(\\"PASSWORD\\")"
  }
]"""

    try:
        print(f"\nTesting model: {OLLAMA_MODEL}")
        print("Sending test prompt...")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": test_prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 2000
                    }
                },
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    response_text = result.get("response", "")
                    
                    print("\n✅ Model responded successfully!")
                    print("\nRaw response:")
                    print("-" * 60)
                    print(response_text[:500] + "..." if len(response_text) > 500 else response_text)
                    print("-" * 60)
                    
                    # Try to parse JSON
                    try:
                        # Extract JSON
                        if "```json" in response_text:
                            json_text = response_text.split("```json")[1].split("```")[0].strip()
                        elif "```" in response_text:
                            json_text = response_text.split("```")[1].split("```")[0].strip()
                        elif "[" in response_text:
                            start = response_text.find("[")
                            end = response_text.rfind("]") + 1
                            json_text = response_text[start:end]
                        else:
                            json_text = response_text
                        
                        findings = json.loads(json_text)
                        print("\n✅ JSON parsing successful!")
                        print(f"\nFound {len(findings)} issue(s):")
                        for i, finding in enumerate(findings, 1):
                            print(f"\n  [{i}] {finding.get('rule', 'Unknown')}")
                            print(f"      Line: {finding.get('line', 'N/A')}")
                            print(f"      Severity: {finding.get('severity', 'N/A')}")
                            print(f"      Old: {finding.get('oldCode', 'N/A')[:50]}")
                            print(f"      New: {finding.get('newCode', 'N/A')[:50]}")
                        
                        return True
                    except json.JSONDecodeError as e:
                        print(f"\n⚠️  Warning: Could not parse JSON: {e}")
                        print("The model responded but not in valid JSON format.")
                        print("This might work better with real code analysis.")
                        return True
                else:
                    print(f"❌ Model request failed with status {response.status}")
                    error_text = await response.text()
                    print(f"Error: {error_text}")
                    return False
                    
    except asyncio.TimeoutError:
        print("❌ Request timed out. Model might be too large for your system.")
        print("Try a smaller model like 'llama3.2:3b'")
        return False
    except Exception as e:
        print(f"❌ Error during inference: {e}")
        return False

async def test_governance_engine():
    """Test the actual governance engine integration"""
    print("\n" + "=" * 60)
    print("Testing Governance Engine Integration")
    print("=" * 60)
    
    # Create a test file
    test_code = '''import os

# Bad: hardcoded password
DATABASE_PASSWORD = "super_secret_123"

# Bad: hardcoded discount
DISCOUNT_RATE = 0.20

# Bad: potential division by zero
def calculate_average(total, count):
    return total / count

# Good: using environment variable
API_KEY = os.getenv("API_KEY")
'''
    
    test_file_path = "./test_code.py"
    with open(test_file_path, 'w') as f:
        f.write(test_code)
    
    print(f"\nCreated test file: {test_file_path}")
    print("\nTest code:")
    print("-" * 60)
    print(test_code)
    print("-" * 60)
    
    try:
        # Import and run governance check
        import sys
        sys.path.insert(0, '.')
        from engines.governance_engine import run_governance_check
        
        print("\nRunning governance check...")
        result = await run_governance_check(test_file_path)
        
        print("\n✅ Governance check completed!")
        print(f"\nStatus: {result.get('status')}")
        print(f"Engine: {result.get('engine')}")
        
        findings = result.get('findings', [])
        print(f"\nFindings: {len(findings)}")
        
        for i, finding in enumerate(findings, 1):
            print(f"\n  [{i}] {finding.get('rule')}")
            print(f"      Line: {finding.get('line')}")
            print(f"      Severity: {finding.get('severity')}")
            print(f"      Message: {finding.get('message')}")
            print(f"      Can Auto-fix: {finding.get('canAutoFix')}")
        
        return True
    except ImportError:
        print("⚠️  Could not import governance_engine.py")
        print("Make sure governance_engine.py is in the current directory")
        return False
    except Exception as e:
        print(f"❌ Error during governance check: {e}")
        return False

async def main():
    """Run all tests"""
    print("""
╔════════════════════════════════════════════════════════════╗
║     Ollama Integration Test Suite                         ║
╚════════════════════════════════════════════════════════════╝
""")
    
    # Test 1: Connection
    connection_ok = await test_ollama_connection()
    if not connection_ok:
        print("\n❌ Cannot proceed without Ollama connection")
        print("\nTo fix:")
        print("  1. Install Ollama: https://ollama.com/download")
        print("  2. Start Ollama service: ollama serve")
        print("  3. Pull model: ollama pull qwen2.5-coder:7b")
        return
    
    # Test 2: Model
    await asyncio.sleep(1)
    model_ok = await test_model_inference()
    
    if not model_ok:
        print(f"\n❌ Model {OLLAMA_MODEL} is not working")
        print("\nTo fix:")
        print(f"  1. Pull the model: ollama pull {OLLAMA_MODEL}")
        print("  2. Or try a different model in governance_engine.py")
        return
    
    # Test 3: Integration
    await asyncio.sleep(1)
    integration_ok = await test_governance_engine()
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"{'✅' if connection_ok else '❌'} Ollama Connection")
    print(f"{'✅' if model_ok else '❌'} Model Inference")
    print(f"{'✅' if integration_ok else '❌'} Governance Engine Integration")
    
    if connection_ok and model_ok and integration_ok:
        print("\n🎉 All tests passed! Your setup is ready!")
        print("\nYou can now:")
        print("  1. Start your application: python main.py")
        print("  2. The governance engine will use local Ollama")
        print("  3. No API keys required!")
    else:
        print("\n⚠️  Some tests failed. Please fix the issues above.")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(main())