"""Canonical concepts, not a tree of interview attack dimensions."""
import re

ALIASES = {
    'racecondition与原子性边界': '并发竞态与原子性边界',
    'racecondition': '并发竞态与原子性边界',
    '竞态条件': '并发竞态与原子性边界',
    'redis的原子性': 'Redis Lua 原子执行',
    'redislua原子执行': 'Redis Lua 原子执行',
    'redislua并发库存扣减': 'Redis Lua 原子执行',
    '幂等性与至少一次执行': '幂等性与至少一次执行',
    '幂等与重试': '幂等性与至少一次执行',
    'rag两阶段检索与reranker': '两阶段检索与候选集上限',
    'reranker无法补救漏召回': '两阶段检索与候选集上限',
    'recall@k、mrr与ndcg': '检索质量指标与相关性标签',
    '受控基线与性能测量': '受控基线与性能测量',
}


def canonical_title(title):
    key = re.sub(r'\s+', '', title.casefold())
    return ALIASES.get(key, title.strip())
