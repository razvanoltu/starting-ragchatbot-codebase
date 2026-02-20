import sys
import os

# Add backend/ to sys.path so all backend modules are importable from tests/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
