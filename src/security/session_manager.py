from __future__ import annotations

import threading
import time


class SessionManager:
    def __init__(
        self,
        session_ttl_minutes: int,
        inactivity_timeout_minutes: int,
        concurrent_sessions_limit: int,
    ):
        self._ttl = session_ttl_minutes * 60
        self._idle = inactivity_timeout_minutes * 60
        self._limit = concurrent_sessions_limit
        self._sessions: dict[str, dict[str, float]] = {}
        self._lock = threading.RLock()

    def _cleanup(self) -> None:
        now = time.time()
        for actor in list(self._sessions):
            sessions = self._sessions[actor]
            for sid in list(sessions):
                started, last_seen = sessions[sid], sessions[sid]
                if now - started > self._ttl or now - last_seen > self._idle:
                    del sessions[sid]
            if not sessions:
                del self._sessions[actor]

    def touch(self, actor: str, session_id: str) -> None:
        now = time.time()
        with self._lock:
            self._cleanup()
            actor_sessions = self._sessions.setdefault(actor, {})
            if session_id not in actor_sessions and len(actor_sessions) >= self._limit:
                raise PermissionError("SESSION_LIMIT_EXCEEDED")
            actor_sessions[session_id] = now

    def active_count(self, actor: str | None = None) -> int:
        with self._lock:
            self._cleanup()
            if actor is None:
                return sum(len(v) for v in self._sessions.values())
            return len(self._sessions.get(actor, {}))
