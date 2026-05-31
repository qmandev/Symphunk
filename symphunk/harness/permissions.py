from enum import Enum

# Tool names verified against live MCP Server v1.2.0 (14 tools, 2026-05-31)
READ_TOOLS = frozenset({
    # splunk_* — confirmed live
    "splunk_run_query",
    "splunk_run_saved_search",
    "splunk_get_indexes",
    "splunk_get_index_info",
    "splunk_get_info",
    "splunk_get_metadata",
    "splunk_get_knowledge_objects",
    "splunk_get_kv_store_collections",
    "splunk_get_user_info",
    "splunk_get_user_list",
    # saia_* — confirmed live
    "saia_generate_spl",
    "saia_explain_spl",
    "saia_optimize_spl",
    "saia_ask_splunk_question",
})

# MCP Server v1.2.0 exposes no write tools — KV writes and dashboard deploy go via REST (kvstore.py / rest.py)
ACTION_TOOLS = frozenset({
    "kv_write",
    "dashboard_deploy",
    "hec_emit",
})


class ActionClass(Enum):
    READ = "read"
    ACTION = "action"


def classify(tool_name: str) -> ActionClass:
    if tool_name in ACTION_TOOLS:
        return ActionClass.ACTION
    return ActionClass.READ


def requires_approval(tool_name: str, severity: str = "low") -> bool:
    if classify(tool_name) == ActionClass.READ:
        return False
    return severity in ("high", "critical")
