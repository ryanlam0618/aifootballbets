import sys
import io

# Simulate user input
input_data = """1
Manchester United vs Tottenham Hotspur
n
"""

# Redirect stdin
sys.stdin = io.StringIO(input_data)

# Run app.py
exec(open('c:/Users/Ryan/python/.vscode/fb_ai_bets/app.py').read())
