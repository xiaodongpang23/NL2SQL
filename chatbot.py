#!/home/xpang/anaconda3/envs/nl2sql/bin/python
import gradio as gr
from agent import Agent

_agent = Agent()

EXAMPLES = [
    "Give me the name of the customer with the highest number of accounts",
    "How many customers are there?",
    "What are the top 5 largest account balances?",
    "Which customers have both a loan and an investment?",
    "Show me the most recent 5 transactions.",
]


def respond(message: str, history: list):
    """Gradio callback. Ignores `history` — Agent maintains its own full history."""
    if not message.strip():
        return history, ""
    answer, sql_used = _agent.chat(message)
    if sql_used is not None:
        response = f"```sql\n{sql_used}\n```\n\n{answer}"
    else:
        response = answer
    history = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": response},
    ]
    return history, ""


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
    gr.Markdown("# Conversational AI-Powered Financial Assistant (NL2SQL)")
    gr.Markdown(
        """**Architectural Challenge:** Enabling non-technical executives to query complex financial relational databases safely.

**Solution:** Reproduced the AWS Bedrock + Redshift pattern locally using Claude API and PostgreSQL. Built a three-layer pipeline: Gradio UI → LLM Tool-Calling Loop → SQL Execution Engine.

**Security & Guardrails:** Engineered a "SELECT-only" SQL guard and 50-row truncation logic to prevent data exfiltration and injection attacks.

**Impact:** Successfully translated natural language into complex JOINs across 6 financial tables (Loans, Investments, Transactions), providing a low-cost alternative to proprietary AWS stacks.

---
**Available tables:** customer, accounts, loans, investments, orders, transactions"""
    )

    chatbot = gr.Chatbot(label="Financial Analytics Assistant", height=450)

    with gr.Row():
        msg = gr.Textbox(
            placeholder="Ask a question about your financial data...",
            show_label=False,
            scale=9,
            lines=1,
            container=False,
        )
        submit_btn = gr.Button("Send", variant="primary", scale=1, min_width=80)

    gr.Markdown("**Example questions:**")
    with gr.Row():
        example_btns = [gr.Button(ex, size="sm", variant="secondary") for ex in EXAMPLES]

    submit_btn.click(respond, [msg, chatbot], [chatbot, msg])
    msg.submit(respond, [msg, chatbot], [chatbot, msg])

    for btn, ex in zip(example_btns, EXAMPLES):
        btn.click(lambda e=ex: e, outputs=msg)

if __name__ == "__main__":
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        theme=custom_theme,
        head="""
        <style>
            body { font-size: 16px !important; }
            .message { font-size: 15px !important; }
        </style>
        """
    )
