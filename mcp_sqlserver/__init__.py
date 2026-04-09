from importlib import import_module
from typing import Any

__all__ = ["server"]


def __getattr__(name: str) -> Any:
	if name == "server":
		return import_module(".server", __name__)
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
