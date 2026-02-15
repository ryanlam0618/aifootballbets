"""
Test Gemini API connection
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

print("=" * 60)
print("Gemini API Test")
print("=" * 60)

# Test importing settings
try:
    from config import settings
    print(f"\n[OK] Settings loaded")
    print(f"   GEMINI_API_KEY: {'*' * len(settings.GEMINI_API_KEY) if settings.GEMINI_API_KEY else 'NOT SET'}")
    print(f"   MODEL_GEMINI: {settings.MODEL_GEMINI}")
except Exception as e:
    print(f"\n[ERROR] Settings: {e}")

# Test importing llm client
try:
    from src.llm_clients import llm
    print(f"\n[OK] LLM client loaded")
except Exception as e:
    print(f"\n[ERROR] LLM client: {e}")

# Test Gemini API call using fetch_data_helper
print("\n[Test 1] Simple Gemini API call (fetch_data_helper)...")
try:
    response = llm.fetch_data_helper("Say 'Hello from Gemini!' in Traditional Chinese, keep it short.")
    print(f"\n[OK] Response:\n{response}")
except Exception as e:
    print(f"\n[ERROR] Gemini API: {e}")

# Test team matching prompt
print("\n[Test 2] Team matching prompt...")
try:
    prompt = """Match this football team name to the closest name in the list:

User input: "Manchester United"
Available names: ["Manchester City", "Manchester United", "Liverpool", "Chelsea", "Arsenal"]

Return ONLY the best matching name from the list, nothing else."""
    
    response = llm.fetch_data_helper(prompt)
    print(f"\n[OK] Response:\n{response}")
except Exception as e:
    print(f"\n[ERROR] Team matching: {e}")

# Test Serie A team matching
print("\n[Test 3] Serie A team matching (Roma vs Cagliari)...")
try:
    prompt = """Match these team names to the closest names in Serie A:

User input: "Roma" and "Cagliari"
Serie A teams: ["AS Roma", "Cagliari", "AC Milan", "Inter Milan", "Juventus", "Napoli", "Lazio", "Fiorentina", "Bologna", "Torino"]

Return in format:
Home: [matched name]
Away: [matched name]"""
    
    response = llm.fetch_data_helper(prompt)
    print(f"\n[OK] Response:\n{response}")
except Exception as e:
    print(f"\n[ERROR] Serie A matching: {e}")

print("\n" + "=" * 60)
print("Test Complete!")
print("=" * 60)
