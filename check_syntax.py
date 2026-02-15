"""
Check app.py syntax
"""
import py_compile
import sys

try:
    py_compile.compile('c:/Users/Ryan/python/.vscode/fb_ai_bets/app.py', doraise=True)
    print("Syntax OK")
except py_compile.PyCompileError as e:
    print(f"Syntax Error: {e}")
    sys.exit(1)
