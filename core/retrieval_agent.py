"""
Retrieval Agent: hybrid search over the documents table.

Pipeline:
  1. Candidates from two independent retrievers, so a document missed by one
     can still be found by the other:
       - semantic: pgvector cosine similarity
       - keyword:  Postgres full-text search
  2. Score every candidate with BM25 (keyword relevance) and cosine
     similarity (semantic relevance).
  3. Combine the two rankings with Reciprocal Rank Fusion (RRF), which avoids
     having to calibrate BM25 scores against cosine scores.
  4. Re-rank with Maximal Marginal Relevance (MMR) so the final top-k chunks
     are relevant AND not near-duplicates of each other.
"""
import math
import re
from collections import Counter

from core import llm
from core.config import config
from core.db import get_connection

CANDIDATES_PER_RETRIEVER = 20
RRF_K = 60
MMR_LAMBDA = 0.7

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "by", "with",
    "is", "are", "was", "were", "be", "did", "do", "does", "why", "what", "how",
    "when", "which", "who", "it", "its", "this", "that", "at", "from", "as",
}


# ----------------------------------------------------------------------
# TEXT + SCORING (pure functions, unit tested)
# ----------------------------------------------------------------------
def tokenize(text: str):
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


def bm25_scores(query: str, docs, k1: float = 1.5, b: float = 0.75):
    """Okapi BM25 over the candidate pool. docs is a list of strings."""
    tokenized = [tokenize(d) for d in docs]
    n = len(tokenized)
    if n == 0:
        return []
    avgdl = sum(len(t) for t in tokenized) / n or 1.0
    df = Counter(term for toks in tokenized for term in set(toks))
    q_terms = set(tokenize(query))

    scores = []
    for toks in tokenized:
        tf = Counter(toks)
        dl = len(toks) or 1
        s = 0.0
        for term in q_terms:
            if term not in tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            s += idf * tf[term] * (k1 + 1) / (tf[term] + k1 * (1 - b + b * dl / avgdl))
        scores.append(s)
    return scores


def cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def ranks(scores):
    """Rank positions (0 = best) for a list of scores."""
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    r = [0] * len(scores)
    for pos, i in enumerate(order):
        r[i] = pos
    return r


def rrf(*rank_lists, k: int = RRF_K):
    n = len(rank_lists[0])
    return [sum(1.0 / (k + rl[i] + 1) for rl in rank_lists) for i in range(n)]


def mmr_select(relevance, embeddings, top_k: int, lambda_: float = MMR_LAMBDA):
    """Greedy MMR. relevance is normalized to 0..1 first."""
    if not relevance:
        return []
    hi, lo = max(relevance), min(relevance)
    rel = [(r - lo) / (hi - lo) if hi > lo else 1.0 for r in relevance]

    selected = []
    remaining = list(range(len(rel)))
    while remaining and len(selected) < top_k:
        def score(i):
            if not selected:
                return rel[i]
            redundancy = max(cosine(embeddings[i], embeddings[j]) for j in selected)
            return lambda_ * rel[i] - (1 - lambda_) * redundancy
        best = max(remaining, key=score)
        selected.append(best)
        remaining.remove(best)
    return selected


# ----------------------------------------------------------------------
# CANDIDATE GENERATION (database)
# ----------------------------------------------------------------------
_COLUMNS = "id::text, content, source, department, entity, embedding"


def _vector_candidates(cur, query_embedding, n):
    cur.execute(
        f"SELECT {_COLUMNS} FROM documents ORDER BY embedding <=> %s::vector LIMIT %s",
        (query_embedding, n),
    )
    return cur.fetchall()


def _keyword_candidates(cur, query, n):
    terms = tokenize(query)
    if not terms:
        return []
    tsquery = " | ".join(terms)  # OR query: any term can match
    cur.execute(
        f"""
        SELECT {_COLUMNS}
        FROM documents
        WHERE to_tsvector('english', content) @@ to_tsquery('english', %s)
        ORDER BY ts_rank_cd(to_tsvector('english', content), to_tsquery('english', %s)) DESC
        LIMIT %s
        """,
        (tsquery, tsquery, n),
    )
    return cur.fetchall()


# ----------------------------------------------------------------------
# MAIN ENTRY
# ----------------------------------------------------------------------
def retrieve(query: str, top_k: int = None, start_index: int = 1) -> dict:
    top_k = top_k or config.TOP_K_RETRIEVAL
    query_embedding, usage = llm.embed(query)

    conn = get_connection()
    try:
        cur = conn.cursor()
        rows = {}
        for r in _vector_candidates(cur, query_embedding, CANDIDATES_PER_RETRIEVER):
            rows[r[0]] = r
        keyword_hits = 0
        for r in _keyword_candidates(cur, query, CANDIDATES_PER_RETRIEVER):
            keyword_hits += 1
            rows.setdefault(r[0], r)
    finally:
        conn.close()

    candidates = list(rows.values())
    if not candidates:
        return {"chunks": [], "llm_usage": [usage], "candidates": 0}

    texts = [c[1] for c in candidates]
    # pgvector returns numpy float32 values; convert so results are JSON-serializable
    embeddings = [[float(x) for x in c[5]] for c in candidates]
    vec_scores = [cosine(query_embedding, e) for e in embeddings]
    kw_scores = bm25_scores(query, texts)
    fused = rrf(ranks(vec_scores), ranks(kw_scores))
    chosen = mmr_select(fused, embeddings, top_k)

    chunks = []
    for i, idx in enumerate(chosen):
        c = candidates[idx]
        chunks.append({
            "evidence_id": f"doc:{start_index + i}",
            "chunk_id": c[0],
            "content": c[1],
            "source": c[2],
            "department": c[3],
            "entity": c[4],
            "vector_score": round(vec_scores[idx], 4),
            "bm25_score": round(kw_scores[idx], 4),
            "rrf_score": round(fused[idx], 5),
        })

    return {"chunks": chunks, "llm_usage": [usage],
            "candidates": len(candidates), "keyword_hits": keyword_hits}
