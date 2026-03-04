from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

base_dir = Path(__file__).resolve().parent.parent
server_path = base_dir / "server.py"
module_name = "mcp_sqlserver._runtime_server"

PUBLIC_API = ["main"]
__all__ = list(PUBLIC_API)

_server: ModuleType | None = None


def _resolve_public_api(module: ModuleType) -> list[str]:
	exported = getattr(module, "__all__", None)
	if isinstance(exported, (list, tuple)):
		return [name for name in exported if isinstance(name, str)]
	return [name for name in PUBLIC_API if name != "main" and hasattr(module, name)]


def _sync_public_api(module: ModuleType) -> list[str]:
	names = _resolve_public_api(module)
	for name in names:
		globals()[name] = getattr(module, name)
	globals()["__all__"] = list(dict.fromkeys(["main", *names]))
	return names


def _load_server() -> ModuleType:
	global _server
	if _server is not None:
		return _server

	if not server_path.is_file():
		raise FileNotFoundError(f"server.py not found at {server_path} (base_dir: {base_dir})")

	spec = importlib.util.spec_from_file_location(module_name, str(server_path))
	if spec is None or spec.loader is None:
		raise ImportError(
			f"Failed to load spec for server.py at {server_path}. "
			f"spec={spec}, loader={getattr(spec, 'loader', None)}"
		)

	module = importlib.util.module_from_spec(spec)
	sys.modules[module_name] = module
	try:
		spec.loader.exec_module(module)
	except Exception as exc:
		sys.modules.pop(module_name, None)
		logging.error("Failed to exec server module at %s: %s", server_path, exc)
		raise

	_server = module
	_sync_public_api(module)
	return module


def main() -> None:
	module = _load_server()
	settings = module.SETTINGS
	logger = module.logger
	mcp = module.mcp

	transport = settings.transport
	logger.info(
		"Starting SQL Server MCP server",
		extra={
			"transport": transport,
			"host": settings.host,
			"port": settings.port,
			"allow_write": settings.allow_write,
		},
	)

	if transport in {"http", "sse"}:
		run_kwargs: dict[str, Any] = {}

		ssl_cert = settings.ssl_cert
		ssl_key = settings.ssl_key
		if ssl_cert or ssl_key:
			if not (ssl_cert and ssl_key):
				raise RuntimeError("Both MCP_SSL_CERT and MCP_SSL_KEY must be set to enable HTTPS.")
			run_kwargs["ssl_certfile"] = ssl_cert
			run_kwargs["ssl_keyfile"] = ssl_key
			logger.info(
				"HTTPS enabled for MCP HTTP transport",
				extra={"ssl_cert": ssl_cert, "ssl_key": ssl_key},
			)

		try:
			mcp.run(transport="http", host=settings.host, port=settings.port, **run_kwargs)
		except TypeError as exc:
			if run_kwargs:
				message = (
					"Current FastMCP runtime does not accept SSL parameters. "
					"Use a reverse proxy for HTTPS termination."
				)
				if settings.ssl_strict:
					raise RuntimeError(message) from exc
				logger.warning("%s Falling back to HTTP without native TLS.", message)
				mcp.run(transport="http", host=settings.host, port=settings.port)
			else:
				raise
	else:
		mcp.run(transport="stdio")


if __name__ == "__main__":
	main()

