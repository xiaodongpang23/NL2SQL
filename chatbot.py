#!/home/xpang/anaconda3/envs/nl2sql/bin/python
import gradio as gr
from agent import Agent

_agent = Agent()


def respond(message: str, history: list) -> str:
    """Gradio callback. Ignores `history` — Agent maintains its own full history."""
    answer, sql_used = _agent.chat(message)
    if sql_used is not None:
        return f"```sql\n{sql_used}\n```\n\n{answer}"
    return answer


custom_theme = gr.themes.Soft(
    primary_hue="blue",
    secondary_hue="slate",
    font=gr.themes.GoogleFont("Inter"),
    font_mono=gr.themes.GoogleFont("IBM Plex Mono"),
).set(
    # Lighter background colors
    body_background_fill="*background_fill_primary",
    background_fill_primary="#FAFBFC",
    background_fill_secondary="#F5F7FA",
    # Softer colors
    block_background_fill="*background_fill_secondary",
    block_border_width="1px",
    block_border_color="*border_color_primary",
    # Better text colors
    body_text_color="*text_color_primary",
    button_primary_background_fill="*primary_500",
    button_primary_background_fill_hover="*primary_600",
    button_primary_text_color="white",
)

with gr.Blocks() as demo:
    gr.ChatInterface(
        fn=respond,
        title="Conversational AI-Powered Financial Assistant (NL2SQL)",
        description="""**Architectural Challenge:** Enabling non-technical executives to query complex financial relational databases safely.

**Solution:** Reproduced the AWS Bedrock + Redshift pattern locally using Claude API and PostgreSQL. Built a three-layer pipeline: Gradio UI → LLM Tool-Calling Loop → SQL Execution Engine.

**Security & Guardrails:** Engineered a "SELECT-only" SQL guard and 50-row truncation logic to prevent data exfiltration and injection attacks.

**Impact:** Successfully translated natural language into complex JOINs across 6 financial tables (Loans, Investments, Transactions), providing a low-cost alternative to proprietary AWS stacks.

---
**Available tables:** customer, accounts, loans, investments, orders, transactions""",
        examples=[
            "Give me the name of the customer with the highest number of accounts",
            "How many customers are there?",
            "What are the top 5 largest account balances?",
            "Which customers have both a loan and an investment?",
            "Show me the most recent 5 transactions.",
        ],
    )

if __name__ == "__main__":
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        theme=custom_theme,
        head="""
        <style>
            body {
                font-size: 16px !important;
            }
            .message {
                font-size: 15px !important;
            }
        </style>
        """
    )
