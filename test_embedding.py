from core.llm import embed

vector, usage = embed("refund issue")
print(len(vector), usage)
