from agent.tools.registry import ToolRegistry, build_default_registry


def test_default_registry_exposes_controlled_runtime_tools():
    registry = build_default_registry()

    assert [tool.metadata.name for tool in registry.list()] == [
        "archive_list",
        "bash",
        "file",
        "file_hash",
        "http_request",
        "python",
        "sandbox_python",
        "web_intelligence",
        "workspace_list",
        "workspace_read_bytes",
        "workspace_read_text",
        "workspace_write_text",
    ]
    assert [schema["name"] for schema in registry.schemas()] == [
        "archive_list",
        "bash",
        "file",
        "file_hash",
        "http_request",
        "python",
        "sandbox_python",
        "web_intelligence",
        "workspace_list",
        "workspace_read_bytes",
        "workspace_read_text",
        "workspace_write_text",
    ]


def test_registry_rejects_duplicate_tool_names():
    registry = ToolRegistry()
    file_tool = build_default_registry().get("file")
    assert file_tool is not None

    registry.register(file_tool)
    try:
        registry.register(file_tool)
    except ValueError as error:
        assert "already registered" in str(error)
    else:
        raise AssertionError("duplicate tool registration must be rejected")
