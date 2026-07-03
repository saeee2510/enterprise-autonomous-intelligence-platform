from openai import OpenAI
import os
import json
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def generate_report(query, fused_graph, verified_graph):

    prompt = f"""
You are an enterprise analytics system.

You are given structured evidence.

Do NOT hallucinate.

Only use provided data.

QUESTION:
{query}

FUSED EVIDENCE:
{json.dumps(fused_graph, indent=2)}

VERIFIED EVIDENCE:
{json.dumps(verified_graph, indent=2)}

Return STRICT JSON:

{{
  "executive_summary": "",
  "root_cause": "",
  "key_metrics": [],
  "timeline": [],
  "risk_level": "low|medium|high",
  "recommendations": [],
  "confidence": 0.0
}}
"""

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a strict enterprise reporting engine."},
            {"role": "user", "content": prompt}
        ]
    )

    return res.choices[0].message.content