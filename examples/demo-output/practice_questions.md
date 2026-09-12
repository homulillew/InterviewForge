# Targeted Practice

## task-k0116430dc8d2: Redis Lua 并发库存扣减

material_gap: 材料待核实：简历自述：设计 Redis + Lua 库存扣减，解决高并发下超卖问题，声称吞吐提升 40%。

Interview evidence: t1

mechanism: 结合秒杀库存服务，Redis 库存扣减中，Lua 的原子性具体保护了哪些状态变化？

Evidence produced: 一段脱离参考答案的解释，含机制、反例和边界

failure_mode: 对Redis Lua 并发库存扣减构造一个失败输入，解释状态变化，并给出可检查的不变量。

Evidence produced: 反例、预期状态、实际结果与原因

implementation: 针对Redis Lua 并发库存扣减，实现可复现并发扣减与超时重试测试，断言库存非负且同一请求最多扣减一次。

Evidence produced: 可运行测试、失败日志、修复说明与运行环境

为 Redis Lua 并发库存扣减 补充对应源码/测试/测量证据，注明能支持的 Claim：c2

## task-k72f53318cdcf: Race condition 与原子性边界

material_gap: 材料待核实：简历自述：设计 Redis + Lua 库存扣减，解决高并发下超卖问题，声称吞吐提升 40%。

Interview evidence: t1, t2, t3, t4, t5, t6

mechanism: 结合秒杀库存服务，Redis 库存扣减中，Lua 的原子性具体保护了哪些状态变化？

Evidence produced: 一段脱离参考答案的解释，含机制、反例和边界

failure_mode: 对Race condition 与原子性边界构造一个失败输入，解释状态变化，并给出可检查的不变量。

Evidence produced: 反例、预期状态、实际结果与原因

implementation: 针对Race condition 与原子性边界，实现可复现并发扣减与超时重试测试，断言库存非负且同一请求最多扣减一次。

Evidence produced: 可运行测试、失败日志、修复说明与运行环境

为 Race condition 与原子性边界 补充对应源码/测试/测量证据，注明能支持的 Claim：c2, c3

## task-kbbcd50aea195: Redis Lua 并发库存扣减：故障边界

material_gap: 材料待核实：简历自述：设计 Redis + Lua 库存扣减，解决高并发下超卖问题，声称吞吐提升 40%。

Interview evidence: t2, t4, t5

mechanism: 上一答提到“核心是把读库存、判断库存和扣减放进同一个 Redis Lua 脚本，让其他请求无法插入这段读写过程”；结合秒杀库存服务，客户端在扣减成功后超时，重试怎样避免重复扣减？

Evidence produced: 一段脱离参考答案的解释，含机制、反例和边界

failure_mode: 对Redis Lua 并发库存扣减：故障边界构造一个失败输入，解释状态变化，并给出可检查的不变量。

Evidence produced: 反例、预期状态、实际结果与原因

implementation: 针对Redis Lua 并发库存扣减：故障边界，实现可复现并发扣减与超时重试测试，断言库存非负且同一请求最多扣减一次。

Evidence produced: 可运行测试、失败日志、修复说明与运行环境

为 Redis Lua 并发库存扣减：故障边界 补充对应源码/测试/测量证据，注明能支持的 Claim：c2

## task-k7c22a9e673cd: Redis Lua 并发库存扣减：故障定位

material_gap: 材料待核实：简历自述：设计 Redis + Lua 库存扣减，解决高并发下超卖问题，声称吞吐提升 40%。

Interview evidence: t3

mechanism: 上一答提到“超时后我首先按原 request_id 查询或重试，复用第一次处理结果”；结合秒杀库存服务，并发增加后吞吐不再增长，P99 却变高，怎么定位瓶颈？

Evidence produced: 一段脱离参考答案的解释，含机制、反例和边界

failure_mode: 对Redis Lua 并发库存扣减：故障定位构造一个失败输入，解释状态变化，并给出可检查的不变量。

Evidence produced: 反例、预期状态、实际结果与原因

implementation: 针对Redis Lua 并发库存扣减：故障定位，实现可复现并发扣减与超时重试测试，断言库存非负且同一请求最多扣减一次。

Evidence produced: 可运行测试、失败日志、修复说明与运行环境

为 Redis Lua 并发库存扣减：故障定位 补充对应源码/测试/测量证据，注明能支持的 Claim：c2

## task-k0cde6ee95e39: Redis Lua 并发库存扣减：正确性与性能评测

material_gap: 材料待核实：简历自述：设计 Redis + Lua 库存扣减，解决高并发下超卖问题，声称吞吐提升 40%。

Interview evidence: t6

mechanism: 上一答提到“补偿本身也要幂等”；结合秒杀库存服务，如果简历写吞吐提升，你会怎样设计可信的对照实验？

Evidence produced: 一段脱离参考答案的解释，含机制、反例和边界

failure_mode: 对Redis Lua 并发库存扣减：正确性与性能评测构造一个失败输入，解释状态变化，并给出可检查的不变量。

Evidence produced: 反例、预期状态、实际结果与原因

implementation: 针对Redis Lua 并发库存扣减：正确性与性能评测，实现可复现并发扣减与超时重试测试，断言库存非负且同一请求最多扣减一次。

Evidence produced: 可运行测试、失败日志、修复说明与运行环境

为 Redis Lua 并发库存扣减：正确性与性能评测 补充对应源码/测试/测量证据，注明能支持的 Claim：c3
