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


demo = gr.ChatInterface(
    fn=respond,
    title="Financial Database Chatbot",
    description="Ask questions about customers, accounts, loans, investments, orders, and transactions.",
    examples=[
        "How many customers are there?",
        "What are the top 5 largest account balances?",
        "Which customers have both a loan and an investment?",
        "Show me the most recent 5 transactions.",
    ],
)

if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860)
