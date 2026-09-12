import pytest
from interview_forge.agents.interviewer import infer_dimension
from interview_forge.schemas.models import Dimension

@pytest.mark.parametrize("text, expected", [
    ("如何用并发压测证明库存没有扣成负数？", (Dimension.evaluation, "evaluation", 4)),
    ("如何设计实验验证超时重试不会重复扣减？", (Dimension.evaluation, "evaluation", 4)),
    ("How would you test that concurrent requests cannot oversell inventory?", (Dimension.evaluation, "evaluation", 4)),
    ("Redis Lua 脚本为什么能防止库存超卖？", (Dimension.mechanism, "mechanism", 2)),
    ("Why does the Lua script prevent concurrent stock updates?", (Dimension.mechanism, "mechanism", 2)),
    ("脚本执行成功但客户端超时，重试怎么办？", (Dimension.failure, "failure", 5)),
    ("为什么选择 Redis 而不是数据库条件更新？", (Dimension.decision, "decision", 3)),
    ("线上指标突然恶化时如何排查根因？", (Dimension.failure, "debugging", 6)),
    ("并发增加后吞吐不再增长，P99却变高，怎么定位瓶颈？", (Dimension.failure, "debugging", 6)),
    ("数据库已经提交但连接断开时，客户端如何拿到最终结果？", (Dimension.failure, "failure", 5)),
    ("如何同时比较Recall@K、NDCG和端到端延迟？", (Dimension.evaluation, "evaluation", 4)),
    ("向量索引如何快速定位最近邻，背后是什么原理？", (Dimension.mechanism, "mechanism", 2)),
])
def test_material_intent_overrides_scheduled_dimension(text, expected):
    assert infer_dimension(text, Dimension.decision) == expected


def test_unknown_intent_preserves_consistent_default_tuple():
    assert infer_dimension("谈谈这个问题？", Dimension.evaluation) == (Dimension.evaluation, "evaluation", 4)
    assert infer_dimension("谈谈这个问题？", Dimension.decision) == (Dimension.decision, "decision", 3)
