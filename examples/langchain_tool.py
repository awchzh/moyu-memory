"""
examples/langchain_tool.py — Use MOYU as a LangChain tool.

Run:
    pip install langchain langchain-openai moyu-memory
    python examples/langchain_tool.py

Shows how to wrap MOYU as LangChain tools and use them in an agent.
"""

from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.tools import Tool
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from moyu_toolkit import agent_memory as mem


def memory_search(query: str) -> str:
    results = mem.search(query, top_k=3)
    return "\n".join(f"[{r['source']}] {r['summary']}" for r in results)


def memory_save(text: str) -> str:
    mem.add_memory(text, source="user")
    return "Saved."


tools = [
    Tool(name="memory_search", func=memory_search, description="Search past memories"),
    Tool(name="memory_save", func=memory_save, description="Save a new memory"),
]

agent = create_openai_tools_agent(
    ChatOpenAI(model="gpt-4o"),
    tools,
    ChatPromptTemplate.from_messages([
        ("system", "You have persistent memory. Use memory_search to recall past conversations and memory_save to remember new facts."),
        ("placeholder", "{agent_scratchpad}"),
    ]),
)

AgentExecutor(agent=agent, tools=tools).invoke({
    "input": "What do you remember about me?"
})
