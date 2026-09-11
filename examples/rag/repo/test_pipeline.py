from pipeline import retrieve


def test_two_stage():
    class Retriever:
        def search(self, query, k):
            return ["irrelevant", "relevant"][:k]
    class Reranker:
        def rank(self, query, documents):
            return list(reversed(documents))
    assert retrieve("question", Retriever(), Reranker(), 2, 1) == ["relevant"]
