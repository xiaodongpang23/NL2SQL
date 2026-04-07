#!/home/xpang/anaconda3/envs/nl2sql/bin/python
import html as html_lib
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


def _render_sidebar(sessions: list[dict], active_id: str | None) -> str:
    """Render sidebar chat list as HTML. Uses data attributes only — JS handles events."""
    if not sessions:
        return '<p class="no-chats">No chats yet</p>'
    parts = ['<div class="sidebar-list">']
    for s in sessions:
        sid = s["id"]
        display = s.get("name") or s.get("preview") or "New conversation"
        label = display[:38] + ("…" if len(display) > 38 else "")
        active_cls = " active" if sid == active_id else ""
        parts.append(
            f'<div class="chat-item{active_cls}"'
            f' data-id="{html_lib.escape(sid, quote=True)}"'
            f' data-name="{html_lib.escape(display, quote=True)}">'
            f'<span class="chat-label">{html_lib.escape(label)}</span>'
            f'<button class="chat-menu-btn" title="Options">···</button>'
            f'</div>'
        )
    parts.append('</div>')
    return ''.join(parts)


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

_CSS = """
body { font-size: 16px !important; }
.message { font-size: 15px !important; }

/* ── Sidebar list ── */
.no-chats { font-size: 13px; color: #999; padding: 8px 10px; }
.sidebar-list { display: flex; flex-direction: column; gap: 2px; padding: 4px 0; }
.chat-item {
    display: flex; align-items: center; border-radius: 6px;
    padding: 0 4px; cursor: pointer; position: relative;
}
.chat-item:hover  { background: rgba(0,0,0,0.05); }
.chat-item.active { background: rgba(59,130,246,0.12); }
.chat-label {
    flex: 1; font-size: 13px; padding: 7px 6px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    cursor: pointer;
}
.chat-item.active .chat-label { font-weight: 500; }
.chat-menu-btn {
    background: none; border: none; cursor: pointer;
    padding: 4px 6px; border-radius: 4px; font-size: 15px;
    color: #777; opacity: 0; flex-shrink: 0; line-height: 1;
    transition: opacity 0.15s;
}
.chat-item:hover .chat-menu-btn,
.chat-item.active .chat-menu-btn { opacity: 1; }
.chat-menu-btn:hover { background: rgba(0,0,0,0.08); color: #333; }

/* ── Context menu ── */
.nlsql-context-menu {
    position: fixed; background: white;
    border: 1px solid #e0e0e0; border-radius: 8px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.15);
    z-index: 99999; min-width: 140px; overflow: hidden;
}
.nlsql-menu-item {
    padding: 10px 16px; cursor: pointer; font-size: 13px;
    display: flex; align-items: center; gap: 8px; user-select: none;
}
.nlsql-menu-item:hover { background: #f5f7fa; }
.nlsql-menu-item.danger { color: #dc2626; }

/* ── Hidden bridge components ── */
#nlsql-action-input, #nlsql-action-btn { display: none !important; }
"""

_JS = """
<script>
(function () {
    'use strict';

    var _menu = null;

    function closeMenu() {
        if (_menu) { _menu.remove(); _menu = null; }
    }

    // ── Trigger a Python action via the hidden Gradio textbox + button ──
    function trigger(action) {
        var wrapper = document.getElementById('nlsql-action-input');
        if (!wrapper) return;
        var input = wrapper.querySelector('input, textarea');
        if (input) {
            var setter = Object.getOwnPropertyDescriptor(
                Object.getPrototypeOf(input), 'value').set;
            setter.call(input, action);
            input.dispatchEvent(new Event('input',  { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
        }
        setTimeout(function () {
            var btn = document.getElementById('nlsql-action-btn');
            if (btn) { var b = btn.querySelector('button'); if (b) b.click(); }
        }, 80);
    }

    // ── Show context menu ──
    function showMenu(event, item) {
        event.stopPropagation();
        closeMenu();

        var id   = item.dataset.id;
        var name = item.dataset.name;

        var m = document.createElement('div');
        m.className = 'nlsql-context-menu';

        var r = document.createElement('div');
        r.className = 'nlsql-menu-item';
        r.innerHTML = '&#9998;&nbsp; Rename';
        r.addEventListener('click', function (e) {
            e.stopPropagation();
            closeMenu();
            var newName = prompt('Rename chat:', name);
            if (newName !== null && newName.trim()) {
                trigger('rename:' + id + ':' + newName.trim());
            }
        });

        var d = document.createElement('div');
        d.className = 'nlsql-menu-item danger';
        d.innerHTML = '&#128465;&nbsp; Delete';
        d.addEventListener('click', function (e) {
            e.stopPropagation();
            closeMenu();
            if (confirm('Delete this chat? This cannot be undone.')) {
                trigger('delete:' + id);
            }
        });

        m.appendChild(r);
        m.appendChild(d);

        // Position below the button
        var rect = event.currentTarget.getBoundingClientRect();
        m.style.top  = (rect.bottom + 4) + 'px';
        m.style.left = Math.min(rect.left, window.innerWidth - 160) + 'px';
        document.body.appendChild(m);
        _menu = m;
    }

    // ── Event delegation — handles dynamically rendered sidebar ──
    document.addEventListener('click', function (e) {
        // Close menu on any outside click
        if (_menu && !e.target.closest('.nlsql-context-menu')) closeMenu();

        var label   = e.target.closest('.chat-label');
        var menuBtn = e.target.closest('.chat-menu-btn');

        if (label) {
            var item = label.closest('.chat-item');
            if (item) {
                document.querySelectorAll('.chat-item').forEach(function (el) {
                    el.classList.remove('active');
                });
                item.classList.add('active');
                trigger('select:' + item.dataset.id);
            }
        } else if (menuBtn) {
            var item2 = menuBtn.closest('.chat-item');
            if (item2) showMenu(e, item2);
        }
    });
})();
</script>
"""

with gr.Blocks(title="Financial Analytics Assistant") as demo:
    gr.Markdown("""# Conversational AI-Powered Financial Assistant (NL2SQL)
**Available tables:** `customer` · `accounts` · `loans` · `investments` · `orders` · `transactions`
*SELECT-only guard · AI SQL verification · 50-row truncation*""")

    with gr.Row(equal_height=False):

        # ── Left sidebar ──────────────────────────────────────────────────
        with gr.Column(scale=1, min_width=220):
            new_chat_btn = gr.Button("+ New Chat", variant="secondary", size="sm")
            sidebar_html = gr.HTML(value="")
            # Hidden bridge: JS writes here, Python reads on button click
            action_input = gr.Textbox(elem_id="nlsql-action-input", visible=True,
                                      show_label=False, max_lines=1)
            action_btn = gr.Button(elem_id="nlsql-action-btn", visible=True)

        # ── Main chat area ────────────────────────────────────────────────
        with gr.Column(scale=4):
            chatbot = gr.Chatbot(label="Financial Analytics Assistant", height=500)
            with gr.Row():
                msg_input = gr.Textbox(
                    placeholder="Ask a question about the financial data…",
                    show_label=False, scale=4,
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

    # ── Event handlers ────────────────────────────────────────────────────

    def on_load(request: gr.Request):
        username = request.username
        sessions = Agent.list_sessions(username, _PROJECT)
        if sessions:
            try:
                agent = Agent.load(username, _PROJECT, sessions[0]["id"])
                _agents[username] = agent
                return _render_sidebar(sessions, sessions[0]["id"]), _rebuild_chatbot(agent)
            except Exception:
                pass
        agent = Agent(user=username, project=_PROJECT)
        _agents[username] = agent
        return _render_sidebar(sessions, None), []

    def on_new_chat(request: gr.Request):
        username = request.username
        _agents[username] = Agent(user=username, project=_PROJECT)
        sessions = Agent.list_sessions(username, _PROJECT)
        return _render_sidebar(sessions, None), []

    def on_action(action: str, request: gr.Request):
        """Handles select / rename / delete actions sent from JS."""
        username = request.username
        active_id = _agents[username].session_id if username in _agents else None

        if action.startswith("select:"):
            session_id = action[7:]
            try:
                agent = Agent.load(username, _PROJECT, session_id)
                _agents[username] = agent
                sessions = Agent.list_sessions(username, _PROJECT)
                return _render_sidebar(sessions, session_id), _rebuild_chatbot(agent)
            except Exception:
                sessions = Agent.list_sessions(username, _PROJECT)
                return _render_sidebar(sessions, active_id), gr.update()

        elif action.startswith("rename:"):
            rest = action[7:]
            colon = rest.find(":")
            if colon == -1:
                return gr.update(), gr.update()
            session_id, new_name = rest[:colon], rest[colon + 1:].strip()
            if new_name:
                Agent.rename_session(username, _PROJECT, session_id, new_name)
            sessions = Agent.list_sessions(username, _PROJECT)
            return _render_sidebar(sessions, active_id), gr.update()

        elif action.startswith("delete:"):
            session_id = action[7:]
            Agent.delete_session(username, _PROJECT, session_id)
            if username in _agents and _agents[username].session_id == session_id:
                _agents.pop(username, None)
            sessions = Agent.list_sessions(username, _PROJECT)
            if sessions:
                try:
                    agent = Agent.load(username, _PROJECT, sessions[0]["id"])
                    _agents[username] = agent
                    return _render_sidebar(sessions, sessions[0]["id"]), _rebuild_chatbot(agent)
                except Exception:
                    pass
            _agents[username] = Agent(user=username, project=_PROJECT)
            return _render_sidebar(sessions, None), []

        return gr.update(), gr.update()

    def respond(message: str, chatbot_history: list, request: gr.Request):
        if not message.strip():
            return "", chatbot_history, gr.update()
        username = request.username
        if username not in _agents:
            _agents[username] = Agent(user=username, project=_PROJECT)
        agent = _agents[username]
        answer, sql_used = agent.chat(message)
        display = _format_response(answer, sql_used)
        sessions = Agent.list_sessions(username, _PROJECT)
        return (
            "",
            chatbot_history + [{"role": "user", "content": message},
                                {"role": "assistant", "content": display}],
            _render_sidebar(sessions, agent.session_id),
        )

    # ── Wire events ───────────────────────────────────────────────────────

    demo.load(on_load, outputs=[sidebar_html, chatbot])
    new_chat_btn.click(on_new_chat, outputs=[sidebar_html, chatbot])
    action_btn.click(on_action, inputs=[action_input], outputs=[sidebar_html, chatbot])
    send_btn.click(respond, inputs=[msg_input, chatbot], outputs=[msg_input, chatbot, sidebar_html])
    msg_input.submit(respond, inputs=[msg_input, chatbot], outputs=[msg_input, chatbot, sidebar_html])


if __name__ == "__main__":
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        auth=authenticate,
        auth_message="Log in to access your Financial Analytics Assistant",
        theme=custom_theme,
        head=_CSS.join(["<style>", "</style>"]) + _JS,
    )
