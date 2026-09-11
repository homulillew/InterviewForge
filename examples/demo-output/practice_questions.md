# Targeted Practice

## task-k0116430dc8d2: Redis Lua 并发库存扣减

material_gap: 材料缺口（不代表用户不会）：尚未提供与当前问题相关的可复现正确性测试或评测结果

Interview evidence: t1

mechanism: 为什么 Redis + Lua 能解决并发库存扣减的原子性问题？

Evidence produced: 一段脱离参考答案的解释，含机制、反例和边界

failure_mode: 对Redis Lua 并发库存扣减构造一个失败输入，解释状态变化，并给出可检查的不变量。

Evidence produced: 反例、预期状态、实际结果与原因

implementation: 针对Redis Lua 并发库存扣减，实现可复现并发扣减与超时重试测试，断言库存非负且同一请求最多扣减一次。

Evidence produced: 可运行测试、失败日志、修复说明与运行环境

为 Redis Lua 并发库存扣减 补充对应源码/测试/测量证据，注明能支持的 Claim：c2

## task-k72f53318cdcf: Race condition 与原子性边界

material_gap: 材料缺口（不代表用户不会）：尚未提供与当前问题相关的可复现正确性测试或评测结果

Interview evidence: t1, t2, t3, t4, t5, t6

mechanism: 为什么 Redis + Lua 能解决并发库存扣减的原子性问题？

Evidence produced: 一段脱离参考答案的解释，含机制、反例和边界

failure_mode: 对Race condition 与原子性边界构造一个失败输入，解释状态变化，并给出可检查的不变量。

Evidence produced: 反例、预期状态、实际结果与原因

implementation: 针对Race condition 与原子性边界，实现可复现并发扣减与超时重试测试，断言库存非负且同一请求最多扣减一次。

Evidence produced: 可运行测试、失败日志、修复说明与运行环境

为 Race condition 与原子性边界 补充对应源码/测试/测量证据，注明能支持的 Claim：c2, c3

## task-k0cde6ee95e39: Redis Lua 并发库存扣减：正确性与性能评测

material_gap: 材料缺口（不代表用户不会）：尚未提供与当前问题相关的可复现正确性测试或评测结果

Interview evidence: t2

mechanism: 上一答提到“读库存、判断和扣减若分成多个请求，会出现交错执行”；如何证明并发扣减没有超卖，并可靠测量吞吐和 P99？

Evidence produced: 一段脱离参考答案的解释，含机制、反例和边界

failure_mode: 对Redis Lua 并发库存扣减：正确性与性能评测构造一个失败输入，解释状态变化，并给出可检查的不变量。

Evidence produced: 反例、预期状态、实际结果与原因

implementation: 针对Redis Lua 并发库存扣减：正确性与性能评测，实现可复现并发扣减与超时重试测试，断言库存非负且同一请求最多扣减一次。

Evidence produced: 可运行测试、失败日志、修复说明与运行环境

为 Redis Lua 并发库存扣减：正确性与性能评测 补充对应源码/测试/测量证据，注明能支持的 Claim：c2

## task-k949b2bdaadf0: Redis Lua 并发库存扣减：选型权衡

material_gap: 材料缺口（不代表用户不会）：尚未提供与当前问题相关的可复现正确性测试或评测结果

Interview evidence: t3, t6

mechanism: 上一答提到“并发提交超过初始库存的请求，检查库存非负且成功数与扣减数一致；注入超时重试和节点故障，检查幂等性及订单对账，再报告吞吐量、P99、客户端数和测试环境”；为什么这里选择 Redis Lua 而不是数据库乐观锁，决策依据是什么？

Evidence produced: 一段脱离参考答案的解释，含机制、反例和边界

failure_mode: 对Redis Lua 并发库存扣减：选型权衡构造一个失败输入，解释状态变化，并给出可检查的不变量。

Evidence produced: 反例、预期状态、实际结果与原因

implementation: 针对Redis Lua 并发库存扣减：选型权衡，实现可复现并发扣减与超时重试测试，断言库存非负且同一请求最多扣减一次。

Evidence produced: 可运行测试、失败日志、修复说明与运行环境

为 Redis Lua 并发库存扣减：选型权衡 补充对应源码/测试/测量证据，注明能支持的 Claim：c2, c3

## task-kbbcd50aea195: Redis Lua 并发库存扣减：故障边界

material_gap: 材料缺口（不代表用户不会）：尚未提供与当前问题相关的可复现正确性测试或评测结果

Interview evidence: t4

mechanism: 上一答提到“比较冲突率、业务事务边界和运维成本”；Redis 执行后客户端超时，如何避免重试导致重复扣减？

Evidence produced: 一段脱离参考答案的解释，含机制、反例和边界

failure_mode: 对Redis Lua 并发库存扣减：故障边界构造一个失败输入，解释状态变化，并给出可检查的不变量。

Evidence produced: 反例、预期状态、实际结果与原因

implementation: 针对Redis Lua 并发库存扣减：故障边界，实现可复现并发扣减与超时重试测试，断言库存非负且同一请求最多扣减一次。

Evidence produced: 可运行测试、失败日志、修复说明与运行环境

为 Redis Lua 并发库存扣减：故障边界 补充对应源码/测试/测量证据，注明能支持的 Claim：c2