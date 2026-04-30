


class TestWrapperIsAlwaysAsync:
    """Every registered tool function must be an awaitable coroutine function."""

    def test_all_instance_1_wrappers_are_async(self, instance_1_tools):
        for tool in instance_1_tools:
            fn = tool.fn
            assert inspect.iscoroutinefunction(fn), (
                f"{tool.name}: wrapper is not async — tool will block the event loop"
            )

    def test_all_instance_2_wrappers_are_async(self, instance_2_tools):
        for tool in instance_2_tools:
            fn = tool.fn
            assert inspect.iscoroutinefunction(fn), (
                f"{tool.name}: wrapper is not async — tool will block the event loop"
            )


class TestSignatureExposure:
    """'instance' and 'progress' must not appear in the exposed signature."""

    def test_instance_1_no_instance_param(self, instance_1_tools):
        for tool in instance_1_tools:
            sig = inspect.signature(tool.fn)
            assert "instance" not in sig.parameters, (
                f"{tool.name}: 'instance' param is visible to MCP clients — "
                "clients could override the injected value"
            )

    def test_instance_2_no_instance_param(self, instance_2_tools):
        for tool in instance_2_tools:
            sig = inspect.signature(tool.fn)
            assert "instance" not in sig.parameters, (
                f"{tool.name}: 'instance' param is visible to MCP clients"
            )

    def test_instance_1_no_progress_param(self, instance_1_tools):
        for tool in instance_1_tools:
            sig = inspect.signature(tool.fn)
            assert "progress" not in sig.parameters, (
                f"{tool.name}: 'progress' param should not be exposed to clients"
            )

    def test_instance_2_no_progress_param(self, instance_2_tools):
        for tool in instance_2_tools:
            sig = inspect.signature(tool.fn)
            assert "progress" not in sig.parameters, (
                f"{tool.name}: 'progress' param should not be exposed to clients"
            )


class TestWrapperNoPositionalArgs:
    """Wrapper signature must NOT accept *args — only **kwargs."""

    def _has_var_positional(self, fn) -> bool:
        for p in inspect.signature(fn).parameters.values():
            if p.kind == inspect.Parameter.VAR_POSITIONAL:
                return True
        return False

    def test_instance_1_wrappers_no_var_positional(self, instance_1_tools):
        for tool in instance_1_tools:
            assert not self._has_var_positional(tool.fn), (
                f"{tool.name}: wrapper accepts *args — positional args risk "
                "injecting 'instance' twice and causing TypeError"
            )

    def test_instance_2_wrappers_no_var_positional(self, instance_2_tools):
        for tool in instance_2_tools:
            assert not self._has_var_positional(tool.fn), (
                f"{tool.name}: wrapper accepts *args — see instance 2 timeout risk"
            )


class TestInstanceInjection:
    """When the wrapper runs, it must inject the correct instance integer."""

    @pytest.mark.asyncio
    async def test_instance_1_injects_correct_instance(self, server_module, instance_1_tools):
        """Verify instance=1 is injected for db_01_ ping tool (no real DB needed)."""
        captured: dict = {}

        async def _fake_ping(**kwargs):
            captured.update(kwargs)
            return {"status": "ok"}

        ping_tool = next(
            (t for t in instance_1_tools if t.name == "db_01_ping"), None
        )
        if ping_tool is None:
            pytest.skip("db_01_ping not registered")

        # Patch the underlying function on the module level
        original = server_module.db_sql2019_ping
        server_module.db_sql2019_ping = _fake_ping
        try:
            await ping_tool.fn()
        finally:
            server_module.db_sql2019_ping = original

        assert captured.get("instance") == 1, (
            f"Expected instance=1, got instance={captured.get('instance')}"
        )

    @pytest.mark.asyncio
    async def test_instance_2_injects_correct_instance(self, server_module, instance_2_tools):
        """Verify instance=2 is injected for db_02_ ping tool."""
        captured: dict = {}

        async def _fake_ping(**kwargs):
            captured.update(kwargs)
            return {"status": "ok"}

        ping_tool = next(
            (t for t in instance_2_tools if t.name == "db_02_ping"), None
        )
        if ping_tool is None:
            pytest.skip("db_02_ping not registered")

        original = server_module.db_sql2019_ping
        server_module.db_sql2019_ping = _fake_ping
        try:
            await ping_tool.fn()
        finally:
            server_module.db_sql2019_ping = original

        assert captured.get("instance") == 2, (
            f"Expected instance=2, got instance={captured.get('instance')}"
        )


class TestNoAsyncioRunInWrapper:
    """
    Source-level check: the wrapper body in server.py must not contain asyncio.run().
    asyncio.run() inside an asyncio.to_thread() call causes a nested event loop
    deadlock that manifests as a hang/timeout on all list_registered_tools calls.
    """

    def test_list_registered_tools_no_asyncio_run(self, server_module):
        import inspect as _inspect
        src = _inspect.getsource(server_module.list_registered_tools)
        assert "asyncio.run(" not in src, (
            "list_registered_tools still contains asyncio.run() — "
            "this deadlocks when called from inside asyncio.to_thread()"
        )

    def test_make_wrapper_no_asyncio_run(self, server_module):
        import inspect as _inspect
        src = _inspect.getsource(server_module._register_dual_instance_tools)
        assert "asyncio.run(" not in src, (
            "_register_dual_instance_tools / make_wrapper contains asyncio.run() "
            "— remove it to prevent nested event-loop deadlock"
        )


class TestTimeingSymmetry:
    """
    Smoke test: both instance wrappers should complete in similar order-of-magnitude
    time when the underlying function is a no-op.  A 10x difference signals something
    structural (lock contention, nested thread launch) rather than DB latency.
    """

    @pytest.mark.asyncio
    async def test_wrapper_overhead_comparable(self, instance_1_tools, instance_2_tools):
        async def _noop(**kwargs):
            return {}

        i1_ping = next((t for t in instance_1_tools if t.name == "db_01_ping"), None)
        i2_ping = next((t for t in instance_2_tools if t.name == "db_02_ping"), None)
        if not i1_ping or not i2_ping:
            pytest.skip("Ping tools not registered")

        import server as _srv
        _srv.db_sql2019_ping = _noop  # patch underlying func

        t0 = time.perf_counter()
        await i1_ping.fn()
        t1_elapsed = time.perf_counter() - t0

        t0 = time.perf_counter()
        await i2_ping.fn()
        t2_elapsed = time.perf_counter() - t0

        ratio = max(t1_elapsed, t2_elapsed) / (min(t1_elapsed, t2_elapsed) + 1e-9)
        assert ratio < 10, (
            f"Instance 2 wrapper overhead is {ratio:.1f}x that of Instance 1 — "
            f"i1={t1_elapsed*1000:.1f}ms  i2={t2_elapsed*1000:.1f}ms. "
            "Possible lock contention or nested thread overhead."
        )
