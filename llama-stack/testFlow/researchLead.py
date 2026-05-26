import logging
from utils import *
from agents.webResearcher import ask_web_researcher

logging.getLogger("httpx").setLevel(logging.INFO)
logging.getLogger("llama_stack_client").setLevel(logging.INFO)

web_research_tool = {
    "name": "ask_web_researcher",
    "description": (
        "Delegate to a web research specialist. Use for any current, factual, "
        "or time-sensitive question (news, events, prices, recent developments). "
        "Returns findings with sources."
    ),
    "parameters": [
        {
            "name": "question",
            "parameter_type": "string",
            "description": "The factual question to research.",
            "required": True,
        }
    ],
}

RESEARCH_LEAD_INSTRUCTIONS = (
    "You are a research lead. You answer questions accurately, using your "
    "tools when a question needs information you cannot reliably know.\n\n"

    "TOOLS:\n"
    "- For anything current, factual, or time-sensitive (news, events, "
    "prices, recent developments), delegate to the web research tool. Do not "
    "answer such questions from memory.\n"
    "- For timeless questions you can answer well yourself (concepts, "
    "definitions, reasoning), answer directly without a tool.\n"
    "- Base every factual claim on what a tool returned. Cite the sources it "
    "gives you. If a tool gave you nothing, say so rather than guessing.\n\n"

    "OUTPUT:\n"
    "- Be concise and direct. Lead with the answer.\n"
    "- Separate what is sourced from what is your own reasoning.\n"
    "- If you are unsure or the sources conflict, say so plainly."
)


def main():
    client = LlamaStackClient(base_url=LLAMA_STACK_URL)
    analyst = Analyst(
        client=client, model=MODEL, instructions=RESEARCH_LEAD_INSTRUCTIONS,
        session_name="research-lead",
        client_tools=[web_research_tool],
    )
    dispatch = {"ask_web_researcher": ask_web_researcher}

    question = "How rich is Toto Wolff"
    print("=== QUESTION ===\n" + question)
    print("\n=== ANALYST ===")
    print(analyst.ask_with_tools(question, dispatch))


if __name__ == "__main__":
    main()
