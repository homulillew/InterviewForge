# Best Answer Cards

## q1: 为什么 Redis + Lua 能解决并发库存扣减的原子性问题？

### Direct Interview Answer

读库存、判断和扣减若分成多个请求，会出现交错执行。把检查和扣减放入同一个 Redis Lua 脚本，可以阻止其他命令在脚本执行期间插入；这种原子执行不等于出错回滚，也不等于跨数据库事务。

选型考虑：比较冲突率、业务事务边界和运维成本。数据库条件更新更贴近持久化事务；Redis Lua 适合短小、同实例内的原子操作，但需要单独处理与订单数据库的一致性。

项目边界：当前项目材料可引用 [e6098a5520314a3]、[ec796696445c541]、[e4fec31a00ed11c]；源码原文另列。源码观察不能独立证明个人贡献、生产规模或提升比例；这些结论需要补充可核验结果。

### Project Grounding

[e6098a5520314a3] stock.lua:1-11 (implementation)

```text
-- Redis Lua: atomic check and decrement within one Redis execution context.
-- Does not implement request deduplication, durable orders or failover guarantees.
local amount = tonumber(ARGV[1])
if amount == nil or amount <= 0 or amount ~= math.floor(amount) then
    return redis.error_reply('invalid amount')
end
local stock = tonumber(redis.call('GET', KEYS[1]) or '0')
if stock < amount then
    return -1
end
return redis.call('DECRBY', KEYS[1], amount)
```

[ec796696445c541] service.py:1-7 (implementation)

```text
"""Illustrative caller; requires a caller-supplied Redis connection."""
from pathlib import Path


def reserve(redis_client, sku: str, amount: int):
    lua = Path(__file__).with_name("stock.lua").read_text()
    return redis_client.eval(lua, 1, "stock:" + sku, amount)
```

[e4fec31a00ed11c] README.md:1-6 (documentation)

```text
# Stock fixture

Redis Lua performs a stock check and decrement. This fixture is intentionally incomplete:
no idempotency key, order database, production deployment or benchmark. The resume's 40%
improvement is a deliberately unsupported claim for InterviewForge's evidence-boundary eval.
Do not execute this fixture as a production service.
```

### Retrieval Rationale (relevance, not proof)

- e6098a5520314a3: 31.931 — question terms: atomic, decrby, lua, redis, stock; claim terms: atomic, decrby, lua, redis, stock; artifact type relevant to question dimension
- ec796696445c541: 23.466 — question terms: lua, redis, reserve, stock; claim terms: lua, redis, reserve, stock; artifact type relevant to question dimension
- e4fec31a00ed11c: 12.0 — question terms: lua, redis, stock; claim terms: lua, redis, stock

### General Technical Knowledge

读库存、判断和扣减若分成多个请求，会出现交错执行。把检查和扣减放入同一个 Redis Lua 脚本，可以阻止其他命令在脚本执行期间插入；这种原子执行不等于出错回滚，也不等于跨数据库事务。

### Decision / Trade-off

比较冲突率、业务事务边界和运维成本。数据库条件更新更贴近持久化事务；Redis Lua 适合短小、同实例内的原子操作，但需要单独处理与订单数据库的一致性。

### Failure Modes

- 脚本过长会阻塞其他请求；运行时错误不回滚先前写入；故障切换可能丢失尚未复制的写；请求超时后重试可能重复扣减；集群多 key 操作需要满足槽位约束。

### Unsupported / Unverified

- 简历陈述仍需核实：设计 Redis + Lua 库存扣减，解决高并发下超卖问题，声称吞吐提升 40%。
- 源代码片段不能独立证明个人 Ownership、生产部署规模、性能提升比例或未展示的容错能力。
- 当前选取证据未包含相关测试或评测；无法确认正确性验证与性能结论。

### Improvement Directions

改进方向（未证明已实现）：并发提交超过初始库存的请求，检查库存非负且成功数与扣减数一致；注入超时重试和节点故障，检查幂等性及订单对账，再报告吞吐量、P99、客户端数和测试环境。

### Likely Follow-ups

为什么这里选择 Redis Lua 而不是数据库乐观锁，决策依据是什么？
如何证明并发扣减没有超卖，并可靠测量吞吐和 P99？
Redis 执行后客户端超时，如何避免重试导致重复扣减？

## q2: 上一答提到“读库存、判断和扣减若分成多个请求，会出现交错执行”；如何证明并发扣减没有超卖，并可靠测量吞吐和 P99？

### Direct Interview Answer

并发提交超过初始库存的请求，检查库存非负且成功数与扣减数一致；注入超时重试和节点故障，检查幂等性及订单对账，再报告吞吐量、P99、客户端数和测试环境。

选型考虑：比较冲突率、业务事务边界和运维成本。数据库条件更新更贴近持久化事务；Redis Lua 适合短小、同实例内的原子操作，但需要单独处理与订单数据库的一致性。

项目边界：当前项目材料可引用 [e6098a5520314a3]、[e4fec31a00ed11c]、[ec796696445c541]；源码原文另列。源码观察不能独立证明个人贡献、生产规模或提升比例；这些结论需要补充可核验结果。

### Project Grounding

[e6098a5520314a3] stock.lua:1-11 (implementation)

```text
-- Redis Lua: atomic check and decrement within one Redis execution context.
-- Does not implement request deduplication, durable orders or failover guarantees.
local amount = tonumber(ARGV[1])
if amount == nil or amount <= 0 or amount ~= math.floor(amount) then
    return redis.error_reply('invalid amount')
end
local stock = tonumber(redis.call('GET', KEYS[1]) or '0')
if stock < amount then
    return -1
end
return redis.call('DECRBY', KEYS[1], amount)
```

[e4fec31a00ed11c] README.md:1-6 (documentation)

```text
# Stock fixture

Redis Lua performs a stock check and decrement. This fixture is intentionally incomplete:
no idempotency key, order database, production deployment or benchmark. The resume's 40%
improvement is a deliberately unsupported claim for InterviewForge's evidence-boundary eval.
Do not execute this fixture as a production service.
```

[ec796696445c541] service.py:1-7 (implementation)

```text
"""Illustrative caller; requires a caller-supplied Redis connection."""
from pathlib import Path


def reserve(redis_client, sku: str, amount: int):
    lua = Path(__file__).with_name("stock.lua").read_text()
    return redis_client.eval(lua, 1, "stock:" + sku, amount)
```

### Retrieval Rationale (relevance, not proof)

- e6098a5520314a3: 11.466 — question terms: atomic; claim terms: atomic, decrby, lua, redis, stock
- e4fec31a00ed11c: 8.079 — question terms: benchmark; claim terms: lua, redis, stock
- ec796696445c541: 4.693 — claim terms: lua, redis, reserve, stock

### General Technical Knowledge

并发提交超过初始库存的请求，检查库存非负且成功数与扣减数一致；注入超时重试和节点故障，检查幂等性及订单对账，再报告吞吐量、P99、客户端数和测试环境。

### Decision / Trade-off

比较冲突率、业务事务边界和运维成本。数据库条件更新更贴近持久化事务；Redis Lua 适合短小、同实例内的原子操作，但需要单独处理与订单数据库的一致性。

### Failure Modes

- 脚本过长会阻塞其他请求；运行时错误不回滚先前写入；故障切换可能丢失尚未复制的写；请求超时后重试可能重复扣减；集群多 key 操作需要满足槽位约束。

### Unsupported / Unverified

- 简历陈述仍需核实：设计 Redis + Lua 库存扣减，解决高并发下超卖问题，声称吞吐提升 40%。
- 源代码片段不能独立证明个人 Ownership、生产部署规模、性能提升比例或未展示的容错能力。
- 当前选取证据未包含相关测试或评测；无法确认正确性验证与性能结论。

### Improvement Directions

改进方向（未证明已实现）：并发提交超过初始库存的请求，检查库存非负且成功数与扣减数一致；注入超时重试和节点故障，检查幂等性及订单对账，再报告吞吐量、P99、客户端数和测试环境。

### Likely Follow-ups

为什么这里选择 Redis Lua 而不是数据库乐观锁，决策依据是什么？
如何证明并发扣减没有超卖，并可靠测量吞吐和 P99？
Redis 执行后客户端超时，如何避免重试导致重复扣减？

## q3: 上一答提到“并发提交超过初始库存的请求，检查库存非负且成功数与扣减数一致；注入超时重试和节点故障，检查幂等性及订单对账，再报告吞吐量、P99、客户端数和测试环境”；为什么这里选择 Redis Lua 而不是数据库乐观锁，决策依据是什么？

### Direct Interview Answer

比较冲突率、业务事务边界和运维成本。数据库条件更新更贴近持久化事务；Redis Lua 适合短小、同实例内的原子操作，但需要单独处理与订单数据库的一致性。

选型考虑：比较冲突率、业务事务边界和运维成本。数据库条件更新更贴近持久化事务；Redis Lua 适合短小、同实例内的原子操作，但需要单独处理与订单数据库的一致性。

项目边界：当前项目材料可引用 [e6098a5520314a3]、[ec796696445c541]、[e4fec31a00ed11c]；源码原文另列。源码观察不能独立证明个人贡献、生产规模或提升比例；这些结论需要补充可核验结果。

### Project Grounding

[e6098a5520314a3] stock.lua:1-11 (implementation)

```text
-- Redis Lua: atomic check and decrement within one Redis execution context.
-- Does not implement request deduplication, durable orders or failover guarantees.
local amount = tonumber(ARGV[1])
if amount == nil or amount <= 0 or amount ~= math.floor(amount) then
    return redis.error_reply('invalid amount')
end
local stock = tonumber(redis.call('GET', KEYS[1]) or '0')
if stock < amount then
    return -1
end
return redis.call('DECRBY', KEYS[1], amount)
```

[ec796696445c541] service.py:1-7 (implementation)

```text
"""Illustrative caller; requires a caller-supplied Redis connection."""
from pathlib import Path


def reserve(redis_client, sku: str, amount: int):
    lua = Path(__file__).with_name("stock.lua").read_text()
    return redis_client.eval(lua, 1, "stock:" + sku, amount)
```

[e4fec31a00ed11c] README.md:1-6 (documentation)

```text
# Stock fixture

Redis Lua performs a stock check and decrement. This fixture is intentionally incomplete:
no idempotency key, order database, production deployment or benchmark. The resume's 40%
improvement is a deliberately unsupported claim for InterviewForge's evidence-boundary eval.
Do not execute this fixture as a production service.
```

### Retrieval Rationale (relevance, not proof)

- e6098a5520314a3: 15.483 — question terms: lua, redis; claim terms: atomic, decrby, lua, redis, stock; artifact type relevant to question dimension
- ec796696445c541: 13.366 — question terms: lua, redis; claim terms: lua, redis, reserve, stock; artifact type relevant to question dimension
- e4fec31a00ed11c: 9.0 — question terms: lua, redis; claim terms: lua, redis, stock

### General Technical Knowledge

比较冲突率、业务事务边界和运维成本。数据库条件更新更贴近持久化事务；Redis Lua 适合短小、同实例内的原子操作，但需要单独处理与订单数据库的一致性。

### Decision / Trade-off

比较冲突率、业务事务边界和运维成本。数据库条件更新更贴近持久化事务；Redis Lua 适合短小、同实例内的原子操作，但需要单独处理与订单数据库的一致性。

### Failure Modes

- 脚本过长会阻塞其他请求；运行时错误不回滚先前写入；故障切换可能丢失尚未复制的写；请求超时后重试可能重复扣减；集群多 key 操作需要满足槽位约束。

### Unsupported / Unverified

- 简历陈述仍需核实：设计 Redis + Lua 库存扣减，解决高并发下超卖问题，声称吞吐提升 40%。
- 源代码片段不能独立证明个人 Ownership、生产部署规模、性能提升比例或未展示的容错能力。
- 当前选取证据未包含相关测试或评测；无法确认正确性验证与性能结论。

### Improvement Directions

改进方向（未证明已实现）：并发提交超过初始库存的请求，检查库存非负且成功数与扣减数一致；注入超时重试和节点故障，检查幂等性及订单对账，再报告吞吐量、P99、客户端数和测试环境。

### Likely Follow-ups

为什么这里选择 Redis Lua 而不是数据库乐观锁，决策依据是什么？
如何证明并发扣减没有超卖，并可靠测量吞吐和 P99？
Redis 执行后客户端超时，如何避免重试导致重复扣减？

## q4: 上一答提到“比较冲突率、业务事务边界和运维成本”；Redis 执行后客户端超时，如何避免重试导致重复扣减？

### Direct Interview Answer

脚本过长会阻塞其他请求；运行时错误不回滚先前写入；故障切换可能丢失尚未复制的写；请求超时后重试可能重复扣减；集群多 key 操作需要满足槽位约束。 读库存、判断和扣减若分成多个请求，会出现交错执行。把检查和扣减放入同一个 Redis Lua 脚本，可以阻止其他命令在脚本执行期间插入；这种原子执行不等于出错回滚，也不等于跨数据库事务。

选型考虑：比较冲突率、业务事务边界和运维成本。数据库条件更新更贴近持久化事务；Redis Lua 适合短小、同实例内的原子操作，但需要单独处理与订单数据库的一致性。

项目边界：当前项目材料可引用 [e6098a5520314a3]、[e4fec31a00ed11c]、[ec796696445c541]；源码原文另列。源码观察不能独立证明个人贡献、生产规模或提升比例；这些结论需要补充可核验结果。

### Project Grounding

[e6098a5520314a3] stock.lua:1-11 (implementation)

```text
-- Redis Lua: atomic check and decrement within one Redis execution context.
-- Does not implement request deduplication, durable orders or failover guarantees.
local amount = tonumber(ARGV[1])
if amount == nil or amount <= 0 or amount ~= math.floor(amount) then
    return redis.error_reply('invalid amount')
end
local stock = tonumber(redis.call('GET', KEYS[1]) or '0')
if stock < amount then
    return -1
end
return redis.call('DECRBY', KEYS[1], amount)
```

[e4fec31a00ed11c] README.md:1-6 (documentation)

```text
# Stock fixture

Redis Lua performs a stock check and decrement. This fixture is intentionally incomplete:
no idempotency key, order database, production deployment or benchmark. The resume's 40%
improvement is a deliberately unsupported claim for InterviewForge's evidence-boundary eval.
Do not execute this fixture as a production service.
```

[ec796696445c541] service.py:1-7 (implementation)

```text
"""Illustrative caller; requires a caller-supplied Redis connection."""
from pathlib import Path


def reserve(redis_client, sku: str, amount: int):
    lua = Path(__file__).with_name("stock.lua").read_text()
    return redis_client.eval(lua, 1, "stock:" + sku, amount)
```

### Retrieval Rationale (relevance, not proof)

- e6098a5520314a3: 11.733 — question terms: redis; claim terms: atomic, decrby, lua, redis, stock; artifact type relevant to question dimension
- e4fec31a00ed11c: 11.079 — question terms: idempotency, redis; claim terms: lua, redis, stock
- ec796696445c541: 9.616 — question terms: redis; claim terms: lua, redis, reserve, stock; artifact type relevant to question dimension

### General Technical Knowledge

脚本过长会阻塞其他请求；运行时错误不回滚先前写入；故障切换可能丢失尚未复制的写；请求超时后重试可能重复扣减；集群多 key 操作需要满足槽位约束。 读库存、判断和扣减若分成多个请求，会出现交错执行。把检查和扣减放入同一个 Redis Lua 脚本，可以阻止其他命令在脚本执行期间插入；这种原子执行不等于出错回滚，也不等于跨数据库事务。

### Decision / Trade-off

比较冲突率、业务事务边界和运维成本。数据库条件更新更贴近持久化事务；Redis Lua 适合短小、同实例内的原子操作，但需要单独处理与订单数据库的一致性。

### Failure Modes

- 脚本过长会阻塞其他请求；运行时错误不回滚先前写入；故障切换可能丢失尚未复制的写；请求超时后重试可能重复扣减；集群多 key 操作需要满足槽位约束。

### Unsupported / Unverified

- 简历陈述仍需核实：设计 Redis + Lua 库存扣减，解决高并发下超卖问题，声称吞吐提升 40%。
- 源代码片段不能独立证明个人 Ownership、生产部署规模、性能提升比例或未展示的容错能力。
- 当前选取证据未包含相关测试或评测；无法确认正确性验证与性能结论。

### Improvement Directions

改进方向（未证明已实现）：并发提交超过初始库存的请求，检查库存非负且成功数与扣减数一致；注入超时重试和节点故障，检查幂等性及订单对账，再报告吞吐量、P99、客户端数和测试环境。

### Likely Follow-ups

为什么这里选择 Redis Lua 而不是数据库乐观锁，决策依据是什么？
如何证明并发扣减没有超卖，并可靠测量吞吐和 P99？
Redis 执行后客户端超时，如何避免重试导致重复扣减？

## q5: 上一答提到“脚本过长会阻塞其他请求；运行时错误不回滚先前写入；故障切换可能丢失尚未复制的写；请求超时后重试可能重复扣减；集群多 key 操作需要满足槽位约束”；库存检查和扣减分成两个请求，为什么会发生 race condition？

### Direct Interview Answer

两个请求都读到同一份旧值再分别写回，会破坏业务不变量。同步必须覆盖完整的读—检查—写。原子性、隔离性和持久性是不同保证，不能由单条命令的原子性推导跨系统一致性。

选型考虑：比较冲突率、业务事务边界和运维成本。数据库条件更新更贴近持久化事务；Redis Lua 适合短小、同实例内的原子操作，但需要单独处理与订单数据库的一致性。

项目边界：当前项目材料可引用 [e6098a5520314a3]、[ec796696445c541]、[e4fec31a00ed11c]；源码原文另列。源码观察不能独立证明个人贡献、生产规模或提升比例；这些结论需要补充可核验结果。

### Project Grounding

[e6098a5520314a3] stock.lua:1-11 (implementation)

```text
-- Redis Lua: atomic check and decrement within one Redis execution context.
-- Does not implement request deduplication, durable orders or failover guarantees.
local amount = tonumber(ARGV[1])
if amount == nil or amount <= 0 or amount ~= math.floor(amount) then
    return redis.error_reply('invalid amount')
end
local stock = tonumber(redis.call('GET', KEYS[1]) or '0')
if stock < amount then
    return -1
end
return redis.call('DECRBY', KEYS[1], amount)
```

[ec796696445c541] service.py:1-7 (implementation)

```text
"""Illustrative caller; requires a caller-supplied Redis connection."""
from pathlib import Path


def reserve(redis_client, sku: str, amount: int):
    lua = Path(__file__).with_name("stock.lua").read_text()
    return redis_client.eval(lua, 1, "stock:" + sku, amount)
```

[e4fec31a00ed11c] README.md:1-6 (documentation)

```text
# Stock fixture

Redis Lua performs a stock check and decrement. This fixture is intentionally incomplete:
no idempotency key, order database, production deployment or benchmark. The resume's 40%
improvement is a deliberately unsupported claim for InterviewForge's evidence-boundary eval.
Do not execute this fixture as a production service.
```

### Retrieval Rationale (relevance, not proof)

- e6098a5520314a3: 18.082 — question terms: decrby, stock; claim terms: atomic, decrby, lua, redis, stock; artifact type relevant to question dimension
- ec796696445c541: 15.966 — question terms: reserve, stock; claim terms: lua, redis, reserve, stock; artifact type relevant to question dimension
- e4fec31a00ed11c: 6.0 — question terms: stock; claim terms: lua, redis, stock

### General Technical Knowledge

两个请求都读到同一份旧值再分别写回，会破坏业务不变量。同步必须覆盖完整的读—检查—写。原子性、隔离性和持久性是不同保证，不能由单条命令的原子性推导跨系统一致性。

### Decision / Trade-off

比较冲突率、业务事务边界和运维成本。数据库条件更新更贴近持久化事务；Redis Lua 适合短小、同实例内的原子操作，但需要单独处理与订单数据库的一致性。

### Failure Modes

- 脚本过长会阻塞其他请求；运行时错误不回滚先前写入；故障切换可能丢失尚未复制的写；请求超时后重试可能重复扣减；集群多 key 操作需要满足槽位约束。

### Unsupported / Unverified

- 简历陈述仍需核实：设计 Redis + Lua 库存扣减，解决高并发下超卖问题，声称吞吐提升 40%。
- 源代码片段不能独立证明个人 Ownership、生产部署规模、性能提升比例或未展示的容错能力。
- 当前选取证据未包含相关测试或评测；无法确认正确性验证与性能结论。

### Improvement Directions

改进方向（未证明已实现）：并发提交超过初始库存的请求，检查库存非负且成功数与扣减数一致；注入超时重试和节点故障，检查幂等性及订单对账，再报告吞吐量、P99、客户端数和测试环境。

### Likely Follow-ups

为什么这里选择 Redis Lua 而不是数据库乐观锁，决策依据是什么？
如何证明并发扣减没有超卖，并可靠测量吞吐和 P99？
Redis 执行后客户端超时，如何避免重试导致重复扣减？

## q6: 上一答提到“两个请求都读到同一份旧值再分别写回，会破坏业务不变量”；结合刚才的边界，如果业务更重视持久化一致性而不是吞吐，你会如何重新选择Redis Lua 并发库存扣减的替代方案？

### Direct Interview Answer

比较冲突率、业务事务边界和运维成本。数据库条件更新更贴近持久化事务；Redis Lua 适合短小、同实例内的原子操作，但需要单独处理与订单数据库的一致性。

选型考虑：比较冲突率、业务事务边界和运维成本。数据库条件更新更贴近持久化事务；Redis Lua 适合短小、同实例内的原子操作，但需要单独处理与订单数据库的一致性。

项目边界：当前项目材料可引用 [e6098a5520314a3]、[ec796696445c541]、[e4fec31a00ed11c]；源码原文另列。源码观察不能独立证明个人贡献、生产规模或提升比例；这些结论需要补充可核验结果。

### Project Grounding

[e6098a5520314a3] stock.lua:1-11 (implementation)

```text
-- Redis Lua: atomic check and decrement within one Redis execution context.
-- Does not implement request deduplication, durable orders or failover guarantees.
local amount = tonumber(ARGV[1])
if amount == nil or amount <= 0 or amount ~= math.floor(amount) then
    return redis.error_reply('invalid amount')
end
local stock = tonumber(redis.call('GET', KEYS[1]) or '0')
if stock < amount then
    return -1
end
return redis.call('DECRBY', KEYS[1], amount)
```

[ec796696445c541] service.py:1-7 (implementation)

```text
"""Illustrative caller; requires a caller-supplied Redis connection."""
from pathlib import Path


def reserve(redis_client, sku: str, amount: int):
    lua = Path(__file__).with_name("stock.lua").read_text()
    return redis_client.eval(lua, 1, "stock:" + sku, amount)
```

[e4fec31a00ed11c] README.md:1-6 (documentation)

```text
# Stock fixture

Redis Lua performs a stock check and decrement. This fixture is intentionally incomplete:
no idempotency key, order database, production deployment or benchmark. The resume's 40%
improvement is a deliberately unsupported claim for InterviewForge's evidence-boundary eval.
Do not execute this fixture as a production service.
```

### Retrieval Rationale (relevance, not proof)

- e6098a5520314a3: 31.931 — question terms: atomic, decrby, lua, redis, stock; claim terms: atomic, decrby, lua, redis, stock; artifact type relevant to question dimension
- ec796696445c541: 23.466 — question terms: lua, redis, reserve, stock; claim terms: lua, redis, reserve, stock; artifact type relevant to question dimension
- e4fec31a00ed11c: 12.0 — question terms: lua, redis, stock; claim terms: lua, redis, stock

### General Technical Knowledge

比较冲突率、业务事务边界和运维成本。数据库条件更新更贴近持久化事务；Redis Lua 适合短小、同实例内的原子操作，但需要单独处理与订单数据库的一致性。

### Decision / Trade-off

比较冲突率、业务事务边界和运维成本。数据库条件更新更贴近持久化事务；Redis Lua 适合短小、同实例内的原子操作，但需要单独处理与订单数据库的一致性。

### Failure Modes

- 脚本过长会阻塞其他请求；运行时错误不回滚先前写入；故障切换可能丢失尚未复制的写；请求超时后重试可能重复扣减；集群多 key 操作需要满足槽位约束。

### Unsupported / Unverified

- 简历陈述仍需核实：设计 Redis + Lua 库存扣减，解决高并发下超卖问题，声称吞吐提升 40%。
- 源代码片段不能独立证明个人 Ownership、生产部署规模、性能提升比例或未展示的容错能力。
- 当前选取证据未包含相关测试或评测；无法确认正确性验证与性能结论。

### Improvement Directions

改进方向（未证明已实现）：并发提交超过初始库存的请求，检查库存非负且成功数与扣减数一致；注入超时重试和节点故障，检查幂等性及订单对账，再报告吞吐量、P99、客户端数和测试环境。

### Likely Follow-ups

为什么这里选择 Redis Lua 而不是数据库乐观锁，决策依据是什么？
如何证明并发扣减没有超卖，并可靠测量吞吐和 P99？
Redis 执行后客户端超时，如何避免重试导致重复扣减？