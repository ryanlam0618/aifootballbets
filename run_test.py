import sys
sys.stdout.reconfigure(encoding='utf-8')
import io

input_data = '''1
Manchester United vs Tottenham Hotspur
n
'''
sys.stdin = io.StringIO(input_data)

import app
app.main()
