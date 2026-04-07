#!/home/xpang/anaconda3/envs/nl2sql/bin/python
import gradio as gr
from auth import authenticate
from agent import Agent

_agents: dict[str, Agent] = {}  # username → active agent

_PROJECT = "default"


def _format_response(answer: str, sql_used: str | None) -> str:
    if sql_used:
        return f"**✓ AI-Verified**\n```sql\n{sql_used}\n```\n\n{answer}"
    return answer


def _load_or_create(username: str) -> Agent:
    """Return the user's existing conversation, or start a new one."""
    sessions = Agent.list_sessions(username, _PROJECT)
    if sessions:
        try:
            return Agent.load(username, _PROJECT, sessions[0]["id"])
        except Exception:
            pass
    return Agent(user=username, project=_PROJECT)


def _rebuild_chatbot(agent: Agent) -> list[tuple[str, str]]:
    return [
        (t["user"], _format_response(t["assistant"], t["sql"]))
        for t in agent.get_display_history()
    ]


custom_theme = gr.themes.Soft(
    primary_hue="blue",
    secondary_hue="slate",
    font=gr.themes.GoogleFont("Inter"),
    font_mono=gr.themes.GoogleFont("IBM Plex Mono"),
).set(
    body_background_fill="*background_fill_primary",
    background_fill_primary="#FAFBFC",
    background_fill_secondary="#F5F7FA",
    block_background_fill="*background_fill_secondary",
    block_border_width="1px",
    block_border_color="*border_color_primary",
    body_text_color="*text_color_primary",
    button_primary_background_fill="*primary_500",
    button_primary_background_fill_hover="*primary_600",
    button_primary_text_color="white",
)

with gr.Blocks(title="Financial Analytics Assistant") as demo:
    gr.Markdown("""# Conversational AI-Powered Financial Assistant (NL2SQL)

**Architectural Challenge:** Enabling non-technical executives to query complex financial relational databases safely.

**Solution:** Reproduced the AWS Bedrock + Redshift pattern locally using Claude API and PostgreSQL. Built a three-layer pipeline: Gradio UI → LLM Tool-Calling Loop → SQL Execution Engine.

**Security & Guardrails:** SELECT-only SQL guard, AI verification pass, and 50-row truncation to prevent data exfiltration.

**Available tables:** `customer`, `accounts`, `loans`, `investments`, `orders`, `transactions`""")

    chatbot = gr.Chatbot(label="Financial Analytics Assistant", height=500)

    with gr.Row():
        msg_input = gr.Textbox(
            placeholder="Ask a question about the financial data…",
            show_label=False,
            scale=4,
        )
        send_btn = gr.Button("Send", variant="primary", scale=1)

    gr.Examples(
        examples=[
            "Give me the name of the customer with the highest number of accounts",
            "How many customers are there?",
            "What are the top 5 largest account balances?",
            "Which customers have both a loan and an investment?",
            "Show me the most recent 5 transactions.",
        ],
        inputs=msg_input,
    )

    def on_load(request: gr.Request):
        username = request.username
        agent = _load_or_create(username)
        _agents[username] = agent
        return _rebuild_chatbot(agent)

    def respond(message: str, chatbot_history: list, request: gr.Request):
        if not message.strip():
            return "", chatbot_history
        username = request.username
        if username not in _agents:
            _agents[username] = _load_or_create(username)
        agent = _agents[username]
        answer, sql_used = agent.chat(message)
        display = _format_response(answer, sql_used)
        return "", chatbot_history + [(message, display)]

    demo.load(on_load, outputs=[chatbot])

    send_btn.click(respond, inputs=[msg_input, chatbot], outputs=[msg_input, chatbot])
    msg_input.submit(respond, inputs=[msg_input, chatbot], outputs=[msg_input, chatbot])


if __name__ == "__main__":
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        auth=authenticate,
        auth_message="Log in to access your Financial Analytics Assistant",
        theme=custom_theme,
        head="""
        <style>
            body { font-size: 16px !important; }
            .message { font-size: 15px !important; }
        </style>
        """,
    )
