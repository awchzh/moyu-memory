"""
examples/openai_assistant.py — Give your OpenAI Assistant persistent memory.

Example:
    python3 openai_assistant.py "What did we talk about last time?"
    python3 openai_assistant.py "Remember that my favorite color is blue"

Requires:
    pip install openai moyu-memory
"""

import sys
from openai import OpenAI
from moyu_toolkit import agent_memory as mem

client = OpenAI()
query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Hello"

# 1. Load relevant past memories
past = mem.search(query, top_k=3)
context = "\n".join(f"- [{m['source']}] {m['summary']}" for m in past)

# 2. Ask AI with memory context
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": f"Relevant memories:\n{context}\nAnswer naturally."},
        {"role": "user", "content": query},
    ],
)
reply = response.choices[0].message.content
print(reply)

# 3. Save the exchange
mem.add_memory(f"Q: {query} A: {reply[:200]}", source="agent_confirmed")
