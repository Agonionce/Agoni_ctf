from agent.runtime.contracts import ActionProposal, ToolCall
from agent.runtime.executor import ToolExecutor


class LegacyBashShapeTool:
    def execute(self, tool_name, arguments):
        return "[exit_code] 7\n[stdout]\nout\n[stderr]\nerr"


def test_executor_normalizes_legacy_bash_result_into_tool_result():
    proposal = ActionProposal(
        "inspect",
        "one action",
        [ToolCall("call-1", "legacy", {})],
    )
    result = ToolExecutor({"legacy": LegacyBashShapeTool()}).execute(proposal)[0]

    assert result.success is False
    assert result.exit_code == 7
    assert result.stdout == "out"
    assert result.stderr == "err"
