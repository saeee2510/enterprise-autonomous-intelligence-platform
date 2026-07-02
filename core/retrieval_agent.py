import numpy as np
from collections import Counter
from core.sql_agent import get_schema  # optional reuse if needed


# -----------------------------
# BASIC TEXT NORMALIZATION
# -----------------------------
def tokenize(text: str):
    return text.lower().split()


# -----------------------------
# BM25-LIKE SCORING (LIGHTWEIGHT)
# -----------------------------
def bm25_score(query, doc):
    query_tokens = tokenize(query)
    doc_tokens = tokenize(doc)

    doc_len = len(doc_tokens) + 1
    avg_len = 50  # stable heuristic

    freq = Counter(doc_tokens)

    score = 0.0

    for term in query_tokens:
        tf = freq.get(term, 0)

        if tf == 0:
            continue

        idf = np.log((1 + avg_len) / (1 + tf)) + 1

        score += tf * idf / doc_len

    return score


# -----------------------------
# KEYWORD BOOST
# -----------------------------
def keyword_boost(query, doc):
    q = query.lower()
    d = doc.lower()

    if q in d:
        return 5.0

    overlap = len(set(q.split()) & set(d.split()))
    return overlap * 1.2


# -----------------------------
# VECTOR SIMILARITY (precomputed embeddings expected)
# -----------------------------
def cosine_sim(a, b):
    a = np.array(a)
    b = np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


# -----------------------------
# HYBRID SCORE
# -----------------------------
def hybrid_score(query, doc_text, doc_embedding, query_embedding):

    vector_score = cosine_sim(query_embedding, doc_embedding)
    bm25 = bm25_score(query, doc_text)
    keyword = keyword_boost(query, doc_text)

    final = (
        0.5 * vector_score +
        0.3 * bm25 +
        0.2 * keyword
    )

    return final


# -----------------------------
# MMR RERANKING (FIXED)
# -----------------------------
def mmr(query, query_embedding, docs, lambda_=0.7, k=5):

    selected = []
    candidates = docs.copy()

    for _ in range(min(k, len(candidates))):

        best_doc = None
        best_score = -1

        for doc in candidates:

            if doc in selected:
                continue

            doc_text = doc[0]
            doc_embedding = doc[3]

            relevance = hybrid_score(query, doc_text, doc_embedding, query_embedding)

            if not selected:
                diversity = 0
            else:
                diversity = max(
                    cosine_sim(doc_embedding, d[3]) for d in selected
                )

            score = lambda_ * relevance - (1 - lambda_) * diversity

            if score > best_score:
                best_score = score
                best_doc = doc

        if best_doc:
            selected.append(best_doc)

    return selected


# -----------------------------
# DEDUP (SEMANTIC LIGHT VERSION)
# -----------------------------
def deduplicate(docs):
    seen = set()
    unique = []

    for d in docs:
        key = d[0][:120].lower()

        if key not in seen:
            seen.add(key)
            unique.append(d)

    return unique


# -----------------------------
# MAIN RETRIEVAL PIPELINE
# -----------------------------
def retrieve(query, query_embedding, docs):

    docs = deduplicate(docs)
    ranked = mmr(query, query_embedding, docs)

    return ranked