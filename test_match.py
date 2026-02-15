#!/usr/bin/env python
"""Test script for Roma vs Cagliari"""
import sys
import io

# Redirect stdin for the import
sys.stdin = io.StringIO("""4
Roma vs Cagliari
4803270


""")

# Now run the app
import app
app.main()
