from symphunk.harness.permissions import classify, requires_approval, ActionClass


def test_read_tools_classified_as_read():
    assert classify("splunk_search") == ActionClass.READ
    assert classify("saia_generate_spl") == ActionClass.READ
    assert classify("splunk_kv_store_lookup") == ActionClass.READ


def test_action_tools_classified_as_action():
    # MCP v1.2.0 exposes no write tools; local action tools only
    assert classify("kv_write") == ActionClass.ACTION
    assert classify("hec_emit") == ActionClass.ACTION
    assert classify("dashboard_deploy") == ActionClass.ACTION


def test_unknown_tool_defaults_to_read():
    assert classify("some_novel_tool") == ActionClass.READ


def test_high_severity_action_requires_approval():
    assert requires_approval("kv_write", severity="high") is True
    assert requires_approval("dashboard_deploy", severity="critical") is True


def test_low_severity_action_no_approval():
    assert requires_approval("splunk_kv_store_upsert", severity="low") is False


def test_reads_never_require_approval():
    assert requires_approval("splunk_search", severity="critical") is False
