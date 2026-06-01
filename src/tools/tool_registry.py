from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolSpec:
    instance: str
    toolname: str

    @property
    def full_name(self) -> str:
        return f"db_{self.instance}_sql2019_{self.toolname}"


def generate_tool_specs(enabled_instances: list[str]) -> list[ToolSpec]:
    specs: list[ToolSpec] = []
    for instance in enabled_instances:
        specs.extend(
            [
                ToolSpec(instance=instance, toolname="select"),
                ToolSpec(instance=instance, toolname="exec_proc"),
                ToolSpec(instance=instance, toolname="latency_report"),
                ToolSpec(instance=instance, toolname="block_report"),
                ToolSpec(instance=instance, toolname="top_queries_report"),
                ToolSpec(instance=instance, toolname="active_sessions_report"),
                ToolSpec(instance=instance, toolname="index_health_report"),
                ToolSpec(instance=instance, toolname="analyze_tab_health"),
                ToolSpec(instance=instance, toolname="analyze_db_data_model"),
                ToolSpec(instance=instance, toolname="analyze_sec_config"),
                ToolSpec(instance=instance, toolname="sessions_dashboard"),
                ToolSpec(instance=instance, toolname="top_statements"),
            ]
        )
    return specs
