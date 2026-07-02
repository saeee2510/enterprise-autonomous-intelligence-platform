import os
import json
from openai import OpenAI
from dotenv import load_dotenv

# -----------------------------
# ENV + CLIENT
# -----------------------------
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# -----------------------------
# PLANNER PROMPT
# -----------------------------
PLANNER_PROMPT = """
You are a deterministic planning engine for an enterprise AI system.

Your job is NOT to answer the question.

Your job is ONLY to produce an execution plan.

RULES:
- DO NOT answer the question
- DO NOT explain anything
- OUTPUT ONLY valid JSON
- NO markdown, NO backticks
- Keep plans minimal and precise
- Use ONLY these tools: sql, retrieval
- NEVER output SQL queries in the "query" field
- "query" must remain the original user question unchanged
- SQL generation belongs to SQL Agent only

TOOL DEFINITIONS:
- sql: use for counts, aggregations, structured metrics
- retrieval: use for logs, emails, tickets, explanations, incidents

OUTPUT FORMAT:
{{
  "query": "...",
  "intent": "sql | retrieval | hybrid",
  "steps": [
    {{
      "step": 1,
      "tool": "sql | retrieval",
      "action": "...",
      "output": "..."
    }}
  ]
}}

USER QUERY:
{query}
"""

# -----------------------------
# ROUTER / PLANNER
# -----------------------------
def route_query(query: str):
    """
    Converts a natural language query into a structured execution plan.
    """

    prompt = PLANNER_PROMPT.format(query=query)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a strict JSON-only planning engine. No explanations."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0
    )

    content = response.choices[0].message.content.strip()

    # -----------------------------
    # SAFE JSON PARSE
    # -----------------------------
    try:
        plan = json.loads(content)
        return plan

    except Exception:
        # -----------------------------
        # FALLBACK PLAN (SAFE MODE)
        # -----------------------------
        return {
            "query": query,
            "intent": "hybrid",
            "steps": [
                {
                    "step": 1,
                    "tool": "retrieval",
                    "action": "fallback retrieval due to parsing failure",
                    "output": "unstructured evidence"
                }
            ]
        }


# -----------------------------
# OPTIONAL DEBUG RUN
# -----------------------------
if __name__ == "__main__":
    q = input("Enter query: ")
    plan = route_query(q)
    print("\n--- EXECUTION PLAN ---\n")
    print(json.dumps(plan, indent=2))