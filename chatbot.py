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


def _rebuild_chatbot(agent: Agent) -> list[dict]:
    msgs = []
    for t in agent.get_display_history():
        msgs.append({"role": "user", "content": t["user"]})
        msgs.append({"role": "assistant", "content": _format_response(t["assistant"], t["sql"])})
    return msgs


def _session_choices(sessions: list[dict]) -> list[tuple[str, str]]:
    result = []
    for s in sessions:
        # User-set name takes priority over auto-generated preview
        display = s.get("name") or s.get("preview") or "New conversation"
        label = display[:42] + ("…" if len(display) > 42 else "")
        result.append((label, s["id"]))
    return result


def _session_display_name(sessions: list[dict], session_id: str) -> str:
    info = next((s for s in sessions if s["id"] == session_id), {})
    return info.get("name") or info.get("preview", "")


# ── Sidebar action helpers (show/hide controls) ───────────────────────────────

def _actions_visible(name: str = ""):
    return (
        gr.update(visible=True, value=name),  # rename_input
        gr.update(visible=True),               # save_name_btn
        gr.update(visible=True),               # delete_btn
    )


def _actions_hidden():
    return (
        gr.update(visible=False, value=""),  # rename_input
        gr.update(visible=False),             # save_name_btn
        gr.update(visible=False),             # delete_btn
    )


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
**Available tables:** `customer` · `accounts` · `loans` · `investments` · `orders` · `transactions`
*SELECT-only guard · AI SQL verification · 50-row truncation*""")

    with gr.Row(equal_height=False):

        # ── Left sidebar ──────────────────────────────────────────────────────
        with gr.Column(scale=1, min_width=220, elem_classes=["sidebar-col"]):
            new_chat_btn = gr.Button("+ New Chat", variant="secondary", size="sm")
            chat_list = gr.Radio(
                choices=[],
                value=None,
                label="Chat History",
                interactive=True,
                elem_classes=["chat-history-list"],
            )
            # Rename / delete controls — hidden until a session is selected
            rename_input = gr.Textbox(
                label="Rename chat",
                placeholder="Enter new name…",
                max_lines=1,
                visible=False,
            )
            with gr.Row():
                save_name_btn = gr.Button("Save", size="sm", visible=False)
                delete_btn = gr.Button("Delete", size="sm", variant="stop", visible=False)

        # ── Main chat area ────────────────────────────────────────────────────
        with gr.Column(scale=4):
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

    # ── Event handlers ────────────────────────────────────────────────────────

    def on_load(request: gr.Request):
        username = request.username
        sessions = Agent.list_sessions(username, _PROJECT)
        if sessions:
            try:
                agent = Agent.load(username, _PROJECT, sessions[0]["id"])
                chatbot_history = _rebuild_chatbot(agent)
                selected = sessions[0]["id"]
                name = _session_display_name(sessions, selected)
            except Exception:
                agent = Agent(user=username, project=_PROJECT)
                chatbot_history = []
                selected = None
                name = ""
        else:
            agent = Agent(user=username, project=_PROJECT)
            chatbot_history = []
            selected = None
            name = ""
        _agents[username] = agent
        choices = _session_choices(sessions)
        ri, sb, db = _actions_visible(name) if selected else _actions_hidden()
        return gr.update(choices=choices, value=selected), chatbot_history, ri, sb, db

    def on_new_chat(request: gr.Request):
        username = request.username
        _agents[username] = Agent(user=username, project=_PROJECT)
        ri, sb, db = _actions_hidden()
        return gr.update(value=None), [], ri, sb, db

    def on_select_session(session_id: str, request: gr.Request):
        if not session_id:
            return [], *_actions_hidden()
        username = request.username
        try:
            agent = Agent.load(username, _PROJECT, session_id)
            _agents[username] = agent
            sessions = Agent.list_sessions(username, _PROJECT)
            name = _session_display_name(sessions, session_id)
            return _rebuild_chatbot(agent), *_actions_visible(name)
        except Exception:
            return [], *_actions_hidden()

    def on_save_name(new_name: str, session_id: str, request: gr.Request):
        if not session_id or not new_name.strip():
            return gr.update()
        username = request.username
        Agent.rename_session(username, _PROJECT, session_id, new_name.strip())
        sessions = Agent.list_sessions(username, _PROJECT)
        return gr.update(choices=_session_choices(sessions), value=session_id)

    def on_delete(session_id: str, request: gr.Request):
        if not session_id:
            return gr.update(), [], *_actions_hidden()
        username = request.username
        Agent.delete_session(username, _PROJECT, session_id)
        sessions = Agent.list_sessions(username, _PROJECT)
        choices = _session_choices(sessions)
        if sessions:
            try:
                agent = Agent.load(username, _PROJECT, sessions[0]["id"])
                _agents[username] = agent
                name = _session_display_name(sessions, sessions[0]["id"])
                return (
                    gr.update(choices=choices, value=sessions[0]["id"]),
                    _rebuild_chatbot(agent),
                    *_actions_visible(name),
                )
            except Exception:
                pass
        # No sessions left — start fresh
        _agents[username] = Agent(user=username, project=_PROJECT)
        return gr.update(choices=choices, value=None), [], *_actions_hidden()

    def respond(message: str, chatbot_history: list, request: gr.Request):
        if not message.strip():
            return "", chatbot_history, gr.update(), *_actions_hidden()
        username = request.username
        if username not in _agents:
            _agents[username] = Agent(user=username, project=_PROJECT)
        agent = _agents[username]
        answer, sql_used = agent.chat(message)
        display = _format_response(answer, sql_used)
        sessions = Agent.list_sessions(username, _PROJECT)
        choices = _session_choices(sessions)
        name = _session_display_name(sessions, agent.session_id)
        return (
            "",
            chatbot_history + [{"role": "user", "content": message},
                                {"role": "assistant", "content": display}],
            gr.update(choices=choices, value=agent.session_id),
            *_actions_visible(name),
        )

    # ── Wire events ───────────────────────────────────────────────────────────

    _sidebar_actions = [rename_input, save_name_btn, delete_btn]

    demo.load(on_load, outputs=[chat_list, chatbot] + _sidebar_actions)

    new_chat_btn.click(on_new_chat, outputs=[chat_list, chatbot] + _sidebar_actions)

    chat_list.change(
        on_select_session,
        inputs=[chat_list],
        outputs=[chatbot] + _sidebar_actions,
    )

    save_name_btn.click(
        on_save_name,
        inputs=[rename_input, chat_list],
        outputs=[chat_list],
    )

    delete_btn.click(
        on_delete,
        inputs=[chat_list],
        outputs=[chat_list, chatbot] + _sidebar_actions,
    )

    send_btn.click(
        respond,
        inputs=[msg_input, chatbot],
        outputs=[msg_input, chatbot, chat_list] + _sidebar_actions,
    )
    msg_input.submit(
        respond,
        inputs=[msg_input, chatbot],
        outputs=[msg_input, chatbot, chat_list] + _sidebar_actions,
    )


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

            /* ── Sidebar chat history list ── */
            .chat-history-list input[type="radio"] { display: none !important; }
            .chat-history-list .wrap {
                flex-direction: column !important;
                gap: 2px !important;
                padding: 4px 0 !important;
            }
            .chat-history-list label {
                padding: 8px 10px !important;
                border-radius: 6px !important;
                font-size: 13px !important;
                line-height: 1.4 !important;
                width: 100% !important;
                cursor: pointer;
                transition: background 0.15s;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .chat-history-list label:hover {
                background: rgba(0, 0, 0, 0.06) !important;
            }
            .sidebar-col { overflow-y: auto; }
        </style>
        """,
    )
