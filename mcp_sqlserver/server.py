
import sys
import os
import importlib.util
import logging

# Find the top-level server.py
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
server_path = os.path.join(base_dir, 'server.py')

# Pre-flight check: ensure server.py exists
if not os.path.isfile(server_path):
	raise FileNotFoundError(f"server.py not found at {server_path} (base_dir: {base_dir})")

spec = importlib.util.spec_from_file_location('server', server_path)
if spec is None or spec.loader is None:
	raise ImportError(f"Failed to load spec for server.py at {server_path}. spec={spec}, loader={getattr(spec, 'loader', None)}")

_server = importlib.util.module_from_spec(spec)
sys.modules['server'] = _server  # Register module before exec to avoid duplicates
try:
	spec.loader.exec_module(_server)
except Exception as e:
	# Undo sys.modules registration if exec fails
	sys.modules.pop('server', None)
	logging.error(f"Failed to exec server module at {server_path}: {e}")
	raise

# Inject all public attributes into this module
for k in dir(_server):
	if not k.startswith('_'):
		globals()[k] = getattr(_server, k)

