"""
Test app.py fixes with Villarreal vs Espanyol
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

print("=" * 60)
print("Testing app.py fixes")
print("=" * 60)

# Test 1: Fotmob API fix
print("\n[Test 1] Fotmob API match_id fix...")
try:
    from src.fotmob_api import FotmobAPI
    api = FotmobAPI(match_id=4837336)
    print(f"   [OK] FotmobAPI created with match_id: {api.match_id}")
except Exception as e:
    print(f"   [ERROR] {e}")

# Test 2: Import app module and check for syntax errors
print("\n[Test 2] Import app.py to check for syntax errors...")
try:
    # We can't fully import app.py because it has input() calls
    # But we can check the syntax
    import ast
    with open('c:/Users/Ryan/python/.vscode/fb_ai_bets/app.py', 'r', encoding='utf-8') as f:
        code = f.read()
    ast.parse(code)
    print("   [OK] app.py syntax is valid")
except SyntaxError as e:
    print(f"   [ERROR] Syntax error: {e}")

# Test 3: Verify target_home variable initialization
print("\n[Test 3] Check target_home initialization...")
with open('c:/Users/Ryan/python/.vscode/fb_ai_bets/app.py', 'r', encoding='utf-8') as f:
    content = f.read()
    
if 'target_home, target_away = odds_home, odds_away' in content:
    print("   [OK] target_home and target_away are initialized before try block")
else:
    print("   [ERROR] target_home/target_away initialization not found")

# Test 4: Verify no api_home/api_away references
print("\n[Test 4] Check for remaining api_home/api_away references...")
if 'api_home' in content or 'api_away' in content:
    print("   [ERROR] Found remaining api_home or api_away references")
else:
    print("   [OK] No api_home/api_away references found")

print("\n" + "=" * 60)
print("Test Complete!")
print("=" * 60)
