from collections import Counter


def corpus_stats(corpus):
    return {
        "cases": len(corpus.cases),
        "independent_samples": len({c.duplicate_group for c in corpus.cases}),
        "source_types": dict(Counter(c.source_type for c in corpus.cases)),
        "questions": sum(len(c.questions) for c in corpus.cases),
        "chains": sum(len(c.chains) for c in corpus.cases),
        "transitions": len(corpus.transitions),
        "answer_conditioned_transitions": sum(t.observed_answer for t in corpus.transitions),
        "patterns": len(corpus.patterns),
        "style_profiles": len(corpus.style_profiles),
        "unknown_company": sum(c.company is None for c in corpus.cases),
    }
