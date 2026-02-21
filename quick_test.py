"""Quick test for test mode"""
import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
import app
print("Calling run_test_mode()...", flush=True)
app.run_test_mode()
print("Done!", flush=True)
