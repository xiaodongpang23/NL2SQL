import json
import pytest
from unittest.mock import MagicMock, patch


def _make_text_response(text: str):
    """Build a mock Anthropic response that returns a plain text answer."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text

    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [text_block]
    return response


def _make_tool_response(tool_id: str, sql: str):
    """Build a mock Anthropic response that calls execute_sql."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = tool_id
    tool_block.name = "execute_sql"
    tool_block.input = {"sql": sql}

    response = MagicMock()
    response.stop_reason = "tool_use"
    response.content = [tool_block]
    return response


# ---------------------------------------------------------------------------
# Existing chat behaviour tests
# _verify_sql is patched to always approve so these tests are unaffected by
# the new verification step.
# ---------------------------------------------------------------------------

@patch("agent.anthropic.Anthropic")
def test_chat_no_tool_call_returns_answer_and_none_sql(mock_cls):
    from agent import Agent

    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_client.messages.create.return_value = _make_text_response("I can only answer database questions.")

    agent = Agent()
    answer, sql = agent.chat("What is the weather?")

    assert isinstance(answer, str)
    assert len(answer) > 0
    assert sql is None


@patch("agent.Agent._verify_sql", return_value=(True, "APPROVED"))
@patch("agent.anthropic.Anthropic")
@patch("agent.run_query")
def test_chat_tool_call_returns_answer_and_sql(mock_run_query, mock_cls, mock_verify):
    from agent import Agent

    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_run_query.return_value = [{"count": 100}]

    mock_client.messages.create.side_effect = [
        _make_tool_response("tool_abc", "SELECT COUNT(*) FROM customer"),
        _make_text_response("There are 100 customers."),
    ]

    agent = Agent()
    answer, sql = agent.chat("How many customers are there?")

    assert answer == "There are 100 customers."
    assert sql == "SELECT COUNT(*) FROM customer"
    mock_run_query.assert_called_once_with("SELECT COUNT(*) FROM customer")


@patch("agent.Agent._verify_sql", return_value=(True, "APPROVED"))
@patch("agent.anthropic.Anthropic")
@patch("agent.run_query")
def test_chat_history_accumulates_across_turns(mock_run_query, mock_cls, mock_verify):
    from agent import Agent

    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_run_query.return_value = [{"count": 5}]

    mock_client.messages.create.side_effect = [
        _make_tool_response("t1", "SELECT COUNT(*) FROM loans"),
        _make_text_response("There are 5 loans."),
        _make_text_response("The total is 5."),
    ]

    agent = Agent()
    agent.chat("How many loans?")
    agent.chat("What was that total again?")

    # Second API call (index 2) should include history from the first turn
    # Turn 1 makes 2 API calls (tool call + answer), so turn 2 is call_args_list[2]
    second_call_messages = mock_client.messages.create.call_args_list[2][1]["messages"]
    roles = [m["role"] for m in second_call_messages]
    assert roles.count("user") >= 2
    assert roles.count("assistant") >= 1
    # Verify the tool result from turn 1 is present in the history
    tool_result_messages = [
        m for m in second_call_messages
        if m["role"] == "user"
        and isinstance(m["content"], list)
        and any(item.get("type") == "tool_result" for item in m["content"])
    ]
    assert len(tool_result_messages) == 1, "Tool result from turn 1 should be in turn 2's history"


@patch("agent.Agent._verify_sql", return_value=(True, "APPROVED"))
@patch("agent.anthropic.Anthropic")
@patch("agent.run_query")
def test_chat_sql_error_is_fed_back_to_claude(mock_run_query, mock_cls, mock_verify):
    from agent import Agent

    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_run_query.side_effect = Exception("relation does not exist")

    mock_client.messages.create.side_effect = [
        _make_tool_response("t1", "SELECT * FROM bad_table"),
        _make_text_response("I couldn't find that table."),
    ]

    agent = Agent()
    answer, sql = agent.chat("Query a bad table")

    # Claude should have been called twice: once for tool call, once after error
    assert mock_client.messages.create.call_count == 2
    # The tool result message in the second call should contain the error
    second_call_messages = mock_client.messages.create.call_args_list[1][1]["messages"]
    tool_result_msg = next(
        m for m in second_call_messages
        if m["role"] == "user"
        and isinstance(m["content"], list)
        and m["content"][0].get("type") == "tool_result"
    )
    assert "relation does not exist" in tool_result_msg["content"][0]["content"]


@patch("agent.Agent._verify_sql", return_value=(True, "APPROVED"))
@patch("agent.anthropic.Anthropic")
@patch("agent.run_query")
def test_chat_returns_after_max_tool_iterations(mock_run_query, mock_cls, mock_verify):
    from agent import Agent

    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_run_query.return_value = [{"count": 1}]

    # Claude requests a tool call 3 times in a row (hitting _MAX_TOOL_ITERATIONS=3),
    # then on the 4th call it would ask again — but the loop stops at 3 and returns.
    # We configure exactly 3 tool responses; the loop should exit after the 3rd.
    mock_client.messages.create.side_effect = [
        _make_tool_response("t1", "SELECT 1"),
        _make_tool_response("t2", "SELECT 1"),
        _make_tool_response("t3", "SELECT 1"),
    ]

    agent = Agent()
    answer, sql = agent.chat("Keep querying")

    # Should have called the API exactly 3 times (the loop limit)
    assert mock_client.messages.create.call_count == 3
    # Should return the fallback string since no text block was ever returned
    assert answer == "I was unable to complete this query."
    # All three SQL calls should be recorded
    assert sql == "SELECT 1\n\nSELECT 1\n\nSELECT 1"


# ---------------------------------------------------------------------------
# SQL verification tests
# ---------------------------------------------------------------------------

@patch("agent.anthropic.Anthropic")
def test_verify_sql_approved(mock_cls):
    from agent import Agent

    mock_client = MagicMock()
    mock_cls.return_value = mock_client

    verify_response = MagicMock()
    verify_response.content = [MagicMock(text="APPROVED")]
    mock_client.messages.create.return_value = verify_response

    agent = Agent()
    approved, msg = agent._verify_sql("How many customers?", "SELECT COUNT(*) FROM customer")

    assert approved is True
    assert "APPROVED" in msg


@patch("agent.anthropic.Anthropic")
def test_verify_sql_rejected(mock_cls):
    from agent import Agent

    mock_client = MagicMock()
    mock_cls.return_value = mock_client

    verify_response = MagicMock()
    verify_response.content = [MagicMock(text="REJECTED: wrong table name used")]
    mock_client.messages.create.return_value = verify_response

    agent = Agent()
    approved, msg = agent._verify_sql("How many customers?", "SELECT COUNT(*) FROM customers")

    assert approved is False
    assert "REJECTED" in msg


@patch("agent.Agent._verify_sql", return_value=(False, "REJECTED: wrong table"))
@patch("agent.anthropic.Anthropic")
@patch("agent.run_query")
def test_rejected_sql_fed_back_to_claude(mock_run_query, mock_cls, mock_verify):
    from agent import Agent

    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_run_query.return_value = []

    mock_client.messages.create.side_effect = [
        _make_tool_response("t1", "SELECT * FROM wrong_table"),
        _make_text_response("I couldn't do that."),
    ]

    agent = Agent()
    answer, sql = agent.chat("Query something")

    # run_query should NOT have been called — verification blocked execution
    mock_run_query.assert_not_called()
    # Claude called twice: once for tool use, once after receiving the rejection
    assert mock_client.messages.create.call_count == 2
    # The tool result sent back to Claude should describe the verification failure
    second_call_messages = mock_client.messages.create.call_args_list[1][1]["messages"]
    tool_result_msg = next(
        m for m in second_call_messages
        if m["role"] == "user"
        and isinstance(m["content"], list)
        and m["content"][0].get("type") == "tool_result"
    )
    assert "SQL verification failed" in tool_result_msg["content"][0]["content"]
    # No verified SQL was executed, so sql_used should be None
    assert sql is None


# ---------------------------------------------------------------------------
# Session persistence tests
# ---------------------------------------------------------------------------

@patch("agent.Agent._verify_sql", return_value=(True, "APPROVED"))
@patch("agent.anthropic.Anthropic")
@patch("agent.run_query")
def test_save_load_roundtrip(mock_run_query, mock_cls, mock_verify, tmp_path, monkeypatch):
    """Agent serialises history to disk and loads it back faithfully."""
    import agent as agent_module

    def mock_convdir(user, project):
        d = tmp_path / "conversations" / user / project
        d.mkdir(parents=True, exist_ok=True)
        return d

    monkeypatch.setattr(agent_module, "_conversations_dir", mock_convdir)

    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_run_query.return_value = [{"count": 1}]

    mock_client.messages.create.side_effect = [
        _make_tool_response("t1", "SELECT COUNT(*) FROM customer"),
        _make_text_response("There is 1 customer."),
    ]

    a = agent_module.Agent(user="testuser", project="proj")
    a.chat("How many customers?")
    session_id = a.session_id

    # Load back — new Agent instance, same session file
    with patch("agent.anthropic.Anthropic") as mock_cls2:
        mock_cls2.return_value = MagicMock()
        b = agent_module.Agent.load("testuser", "proj", session_id)

    turns = b.get_display_history()
    assert len(turns) == 1
    assert turns[0]["user"] == "How many customers?"
    assert "1 customer" in turns[0]["assistant"]
    assert turns[0]["sql"] == "SELECT COUNT(*) FROM customer"
