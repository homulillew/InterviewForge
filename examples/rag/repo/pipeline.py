"""Two-stage retrieval with injected components; no assumed model architecture."""


def retrieve(query, retriever, reranker, top_k=20, final_k=5):
    if top_k < 1 or final_k < 1 or final_k > top_k:
        raise ValueError("invalid candidate limits")
    candidates = retriever.search(query, k=top_k)
    ranked = reranker.rank(query, candidates)
    return ranked[:final_k]
