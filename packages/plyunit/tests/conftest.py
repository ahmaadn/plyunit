import sys
from unittest.mock import MagicMock

# Mock raylib and pyray to prevent CFFI load errors during test collection
mock_module = MagicMock()
sys.modules['raylib'] = mock_module
sys.modules['raylib._raylib_cffi'] = mock_module
sys.modules['raylib._raylib_cffi.lib'] = mock_module
sys.modules['pyray'] = mock_module
