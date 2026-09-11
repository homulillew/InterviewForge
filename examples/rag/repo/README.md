# Retrieval fixture

The pipeline calls first-stage retrieval followed by reranking. Ranker implementations
are injected; this code does not identify a model family. A unit test demonstrates wiring,
not retrieval-quality improvement. There is no labeled dataset or full benchmark.
