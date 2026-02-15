#!/usr/bin/env python
"""Debug test script for Roma vs Cagliari"""
import sys
import io

# Create input
inputs = """4
Roma vs Cagliari
4803270


"""

# Write inputs to a temp file
with open('debug_inputs.txt', 'w') as f:
    f.write(inputs)

print('Test script started', flush=True)
sys.stderr.flush()

# Now run a minimal test
import subprocess
result = subprocess.run(
    [sys.executable, '-c', '''
import sys
sys.stderr.write("Starting import...\\n")
sys.stderr.flush()
try:
    from app import simple_fuzzy_match, get_odds_api_teams
    sys.stderr.write("Imports OK\\n")
    sys.stderr.flush()
    # Test simple_fuzzy_match
    result = simple_fuzzy_match("Roma", ["Roma", "Cagliari", "Juventus"])
    sys.stderr.write("Fuzzy match result: " + str(result) + "\\n")
    sys.stderr.flush()
except Exception as e:
    sys.stderr.write("Error: " + str(e) + "\\n")
    import traceback
    traceback.print_exc(file=sys.stderr)
'''],
    cwd="c:/Users/Ryan/python/.vscode/fb_ai_bets",
    capture_output=True,
    text=True
)

print('=== STDOUT ===')
print(result.stdout)
print('=== STDERR ===')
print(result.stderr)
print('=== Exit Code: ' + str(result.returncode) + ' ===')
