#!/home/xpang/anaconda3/envs/nl2sql/bin/python
import gradio as gr
from auth import authenticate
from agent import Agent

# One active Agent per logged-in user (keyed by username).
_agents: dict[str, Agent] = {}


def _format_response(answer: str, sql_used: str | None) -> str:
    if sql_used:
        return f"**✓ AI-Verified**\n```sql\n{sql_used}\n```\n\n{answer}"
    return answer


def _session_label(session: dict) -> str:
    dt = session["updated_at"][:16].replace("T", " ")
    preview = session["preview"]
    label = preview[:45] + ("…" if len(preview) > 45 else "")
    return f"{dt} — {label}"


def _rebuild_chatbot(agent: Agent) -> list[tuple[str, str]]:
    """Convert agent display turns → Gradio chatbot history format."""
    result = []
    for turn in agent.get_display_history():
        display = _format_response(turn["assistant"], turn["sql"])
        result.append((turn["user"], display))
    return result


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

with gr.Blocks(title="Financial Analytics Assistant", theme=custom_theme) as demo:
    gr.Markdown("""# Conversational AI-Powered Financial Assistant (NL2SQL)

**Architectural Challenge:** Enabling non-technical executives to query complex financial relational databases safely.

**Solution:** Reproduced the AWS Bedrock + Redshift pattern locally using Claude API and PostgreSQL. Built a three-layer pipeline: Gradio UI → LLM Tool-Calling Loop → SQL Execution Engine.

**Security & Guardrails:** Engineered a "SELECT-only" SQL guard, an AI SQL verification pass, and 50-row truncation logic to prevent data exfiltration and injection attacks.

**Available tables:** `customer`, `accounts`, `loans`, `investments`, `orders`, `transactions`""")

    # ── Project management row ──────────────────────────────────────────
    with gr.Row():
        project_dd = gr.Dropdown(
            label="Project",
            choices=[],
            interactive=True,
            scale=2,
        )
        new_project_input = gr.Textbox(
            placeholder="New project name…",
            show_label=False,
            scale=2,
        )
        create_project_btn = gr.Button("Create Project", scale=1)

    # ── Session management row ──────────────────────────────────────────
    with gr.Row():
        session_dd = gr.Dropdown(
            label="Conversation",
            choices=[],
            value=None,
            interactive=True,
            scale=3,
        )
        new_conv_btn = gr.Button("New Conversation", scale=1)

    # ── Chat area ───────────────────────────────────────────────────────
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

    # ── Event handlers ──────────────────────────────────────────────────

    def on_load(request: gr.Request):
        """Initialise UI for the logged-in user on page load."""
        username = request.username
        projects = Agent.list_projects(username)
        if not projects:
            Agent.create_project(username, "default")
            projects = ["default"]

        first_project = projects[0]
        sessions = Agent.list_sessions(username, first_project)

        if sessions:
            try:
                agent = Agent.load(username, first_project, sessions[0]["id"])
                chatbot_history = _rebuild_chatbot(agent)
                session_value = sessions[0]["id"]
            except Exception:
                agent = Agent(user=username, project=first_project)
                chatbot_history = []
                session_value = None
        else:
            agent = Agent(user=username, project=first_project)
            chatbot_history = []
            session_value = None

        _agents[username] = agent
        session_choices = [(_session_label(s), s["id"]) for s in sessions]

        return (
            gr.update(choices=projects, value=first_project),
            gr.update(choices=session_choices, value=session_value),
            chatbot_history,
        )

    def on_project_change(project: str, request: gr.Request):
        """Load the most recent session when the user switches projects."""
        if not project:
            return gr.update(choices=[], value=None), []
        username = request.username
        sessions = Agent.list_sessions(username, project)

        if sessions:
            try:
                agent = Agent.load(username, project, sessions[0]["id"])
                chatbot_history = _rebuild_chatbot(agent)
                session_value = sessions[0]["id"]
            except Exception:
                agent = Agent(user=username, project=project)
                chatbot_history = []
                session_value = None
        else:
            agent = Agent(user=username, project=project)
            chatbot_history = []
            session_value = None

        _agents[username] = agent
        session_choices = [(_session_label(s), s["id"]) for s in sessions]

        return (
            gr.update(choices=session_choices, value=session_value),
            chatbot_history,
        )

    def on_create_project(name: str, request: gr.Request):
        """Create a new project and switch to it."""
        name = name.strip()
        # Reject empty names or anything that could escape the directory
        if not name or any(c in name for c in r'/\..'):
            return gr.update(), gr.update(), "", []

        username = request.username
        Agent.create_project(username, name)
        projects = Agent.list_projects(username)
        _agents[username] = Agent(user=username, project=name)

        return (
            gr.update(choices=projects, value=name),
            gr.update(choices=[], value=None),
            "",   # clear the new-project text input
            [],   # clear chatbot
        )

    def on_load_session(session_id: str, project: str, request: gr.Request):
        """Load a specific past session into the chat display."""
        if not session_id or not project:
            return []
        username = request.username
        try:
            agent = Agent.load(username, project, session_id)
            _agents[username] = agent
            return _rebuild_chatbot(agent)
        except Exception:
            return []

    def on_new_conversation(project: str, request: gr.Request):
        """Start a fresh conversation in the current project."""
        username = request.username
        _agents[username] = Agent(user=username, project=project or "default")
        return gr.update(value=None), []

    def respond(message: str, chatbot_history: list, project: str, request: gr.Request):
        """Send a user message and append the response to the chat display."""
        if not message.strip():
            return "", chatbot_history, gr.update()

        username = request.username
        current_project = project or "default"
        if username not in _agents:
            _agents[username] = Agent(user=username, project=current_project)

        agent = _agents[username]
        answer, sql_used = agent.chat(message)
        display = _format_response(answer, sql_used)
        chatbot_history = chatbot_history + [(message, display)]

        # Refresh the session dropdown so the new/updated session appears
        sessions = Agent.list_sessions(username, current_project)
        session_choices = [(_session_label(s), s["id"]) for s in sessions]

        return (
            "",                                                        # clear input
            chatbot_history,
            gr.update(choices=session_choices, value=agent.session_id),
        )

    # ── Wire events ─────────────────────────────────────────────────────

    demo.load(
        on_load,
        outputs=[project_dd, session_dd, chatbot],
    )

    project_dd.change(
        on_project_change,
        inputs=[project_dd],
        outputs=[session_dd, chatbot],
    )

    create_project_btn.click(
        on_create_project,
        inputs=[new_project_input],
        outputs=[project_dd, session_dd, new_project_input, chatbot],
    )

    session_dd.change(
        on_load_session,
        inputs=[session_dd, project_dd],
        outputs=[chatbot],
    )

    new_conv_btn.click(
        on_new_conversation,
        inputs=[project_dd],
        outputs=[session_dd, chatbot],
    )

    send_btn.click(
        respond,
        inputs=[msg_input, chatbot, project_dd],
        outputs=[msg_input, chatbot, session_dd],
    )

    msg_input.submit(
        respond,
        inputs=[msg_input, chatbot, project_dd],
        outputs=[msg_input, chatbot, session_dd],
    )


if __name__ == "__main__":
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        auth=authenticate,
        auth_message="Log in to access your Financial Analytics Assistant",
        head="""
        <style>
            body { font-size: 16px !important; }
            .message { font-size: 15px !important; }
        </style>
        """,
    )
