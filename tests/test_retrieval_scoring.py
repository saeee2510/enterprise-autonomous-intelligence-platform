from core.retrieval_agent import bm25_scores, cosine, mmr_select, ranks, rrf, tokenize


def test_tokenize_drops_stopwords():
    assert tokenize("Why did the revenue drop in Europe?") == ["revenue", "drop", "europe"]


def test_bm25_prefers_matching_document():
    docs = ["duplicate payment charged twice in europe",
            "dashboard latency incident in apac",
            "spring campaign discount in north america"]
    scores = bm25_scores("duplicate charge europe", docs)
    assert scores[0] == max(scores)
    assert scores[1] == 0


def test_rrf_rewards_agreement_between_retrievers():
    vec = ranks([0.9, 0.8, 0.1])
    kw = ranks([5.0, 0.0, 1.0])
    fused = rrf(vec, kw)
    assert fused[0] == max(fused)


def test_mmr_avoids_near_duplicates():
    embeddings = [[1, 0], [0.99, 0.01], [0, 1]]
    relevance = [1.0, 0.95, 0.6]
    chosen = mmr_select(relevance, embeddings, top_k=2, lambda_=0.5)
    assert chosen[0] == 0
    assert chosen[1] == 2  # skips the near-duplicate of doc 0


def test_cosine_bounds():
    assert abs(cosine([1, 0], [1, 0]) - 1) < 1e-9
    assert abs(cosine([1, 0], [0, 1])) < 1e-9
