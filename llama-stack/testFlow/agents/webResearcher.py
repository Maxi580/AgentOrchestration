import os
import logging
from tavily import TavilyClient
from utils import Analyst, MODEL, TAVILY_KEY, client

_tavily = TavilyClient(api_key=TAVILY_KEY)

logging.getLogger("httpx").setLevel(logging.INFO)
logging.getLogger("llama_stack_client").setLevel(logging.INFO)

web_search_tool = {
    "name": "web_search",
    "description": "Search the web and return results with titles, content, and URLs.",
    "parameters": [
        {"name": "query", "parameter_type": "string",
         "description": "The search query, 1-6 words.", "required": True}
    ],
}

WEB_RESEARCHER_INSTRUCTIONS = (
    "You are a web research specialist. You answer factual questions by "
    "searching the web and reporting what you find.\n\n"

    "RULES:\n"
    "- Always use the web_search tool. Do not answer from memory.\n"
    "- Report only what the search results say. Include the source for each "
    "claim.\n"
    "- If results are thin, conflicting, or don't answer the question, say so "
    "plainly. Do not fill gaps with guesses.\n"
    "- Be concise and factual. Output is consumed by a research lead, not the "
    "end user."
)


def web_search(query):
    print(f"[WEB_SEARCH] called with query: {query}")
    try:
        res = _tavily.search(query, max_results=5)
        print(f"[WEB_SEARCH] got {len(res['results'])} results")
        out = "\n\n".join(
            f"{r['title']}\n{r['url']}\n{r['content']}" for r in res["results"]
        )
        print(f"[WEB_SEARCH] returning:\n{out[:500]}")
        return out
    except Exception as e:
        print(f"[WEB_SEARCH ERROR] {type(e).__name__}: {e}")
        return f"Search failed: {e}"


web_researcher = Analyst(
    client=client,
    model=MODEL,
    instructions=WEB_RESEARCHER_INSTRUCTIONS,
    session_name="web-researcher",
    client_tools=[web_search_tool],
)


def ask_web_researcher(question):
    return web_researcher.ask_with_tools(
        question, {"web_search": web_search}
    )
