#!/usr/bin/env python
"""Simple runner for app.py"""
import sys
import io
import threading
import time

# Set up inputs
sys.stdin = io.StringIO("""4
Roma vs Cagliari
4803270


""")

# Create a flag to track completion
completed = False
result = None
error = None

def run_app():
    global completed, result, error
    try:
        import app
        app.main()
        completed = True
    except Exception as e:
        error = e
        import traceback
        traceback.print_exc()

# Run in a thread with timeout
def timeout_handler():
    time.sleep(25)  # 25 seconds timeout
    if not completed:
        print("\n\n=== TIMEOUT (25s) ===", flush=True)
        print("The app appears to be hanging or waiting for input.")
        sys.exit(1)

# Start timeout thread
t = threading.Thread(target=timeout_handler)
t.daemon = True
t.start()

# Run the app
try:
    import app
    print("Starting app.main()...", flush=True)
    sys.stdout.flush()
    app.main()
    print("app.main() completed", flush=True)
except KeyboardInterrupt:
    print("\n\n=== INTERRUPTED ===", flush=True)
except Exception as e:
    print("\n\n=== ERROR ===", flush=True)
    print(str(e), flush=True)
    import traceback
    traceback.print_exc()
