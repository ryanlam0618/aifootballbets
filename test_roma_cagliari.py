import sys
sys.stdout.reconfigure(encoding='utf-8')
import io

# Input for Roma vs Cagliari (Serie A)
# League: Serie A = 4
# Match: Roma vs Cagliari
# Fotmob ID: Enter 'n' to skip
input_data = '''4
Roma vs Cagliari
n
'''
sys.stdin = io.StringIO(input_data)

import app
app.main()
