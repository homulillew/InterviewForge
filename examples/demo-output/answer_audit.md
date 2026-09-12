# Answer Reasoning and Source Audit

## t1 · 结合秒杀库存服务，Redis 库存扣减中，Lua 的原子性具体保护了哪些状态变化？

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

### Reasoning Basis

简历项目与能力：秒杀库存服务 / Redis Lua 并发库存扣减
源码依据：[e6098a5520314a3] stock.lua:1
源码依据：[ec796696445c541] service.py:1
源码依据：[e4fec31a00ed11c] README.md:1
参考方法：[item_d2587ee205a66af96880] Redis Lua 脚本为什么能防止库存超卖？
参考方法：[item_6fc0945c96303bd1e208] 如何设计幂等键，避免重复扣库存？
工程细节与实验参数按问题场景推演；实验参数不表示已测得的结果。

### Inferred Design Details

实现上我会用 request_id 标识一次业务请求：脚本先检查幂等结果，再检查库存，最后完成扣减并保存结果；重复请求直接返回第一次的结果。参数类型和取值在写入前检查，库存 key 和幂等 key 在集群里使用同一个 hash tag。
具体处理时，我会采用这个流程：把库存检查、幂等键检查和扣减放入同一段 Lua 脚本，以订单号作为业务幂等键。
具体处理时，我会采用这个流程：幂等键使用订单号并记录处理结果，重试时先返回原结果；库存键和幂等键使用同一个 hash tag 保证落在同一槽位。
具体处理时，我会采用这个流程：客户端超时不能证明服务端失败，重试沿用同一个订单号，先读已保存的处理结果。

### Experiment Plan

实验上，我会这样安排：固定初始库存为 100，使用 200 个并发请求争抢，并让同一订单号重复发起 3 次。
验证时，我会检查：成功订单不超过 100，库存不为负，重复订单只有一次扣减。
实验上，我会这样安排：在发送成功响应前注入延迟，让客户端以 50 毫秒超时重试；分别覆盖脚本执行前断连、执行后响应丢失、幂等记录过期，检查重试返回值和库存是否一致。
性能实验把数据库条件更新作为基线，固定机器、连接池和请求分布，逐档增加并发，同时记录成功吞吐、拒绝率、P95/P99、Redis CPU 和连接等待时间，观察瓶颈出现在哪一档。

### Unsupported / Unverified

简历自述：设计 Redis + Lua 库存扣减，解决高并发下超卖问题，声称吞吐提升 40%。
源代码片段不能独立证明个人 Ownership、生产部署规模、性能提升比例或未展示的容错能力。
当前选取证据未包含相关测试或评测；实验方案与执行结果分别记录。
参考回答只提供方法和表达结构；其中的个人经历、部署规模与测量结果不归属于候选人。

### Reference item_593743c4abe06c46b3e6

examples/materials/interview.md · lines:5-7

```text
Q: Redis 库存扣减中，Lua 的原子性具体保护了哪些状态变化？
追问：客户端在扣减成功后超时，重试怎样避免重复扣减？
追问：脚本执行到一半出错时，已经执行的写入会发生什么？
```

### Reference item_d2587ee205a66af96880

examples/materials/redis-answer.docx · paragraph:1 → paragraph:5

```text
问题：Redis Lua 脚本为什么能防止库存超卖？
回答：我把库存检查、幂等键检查和扣减放入同一段 Lua 脚本，以订单号作为业务幂等键。客户端超时不能证明服务端失败，重试沿用同一个订单号，先读已保存的处理结果。
实验设计：固定初始库存为 100，使用 200 个并发请求争抢，并让同一订单号重复发起 3 次。断言成功订单不超过 100，库存不为负，重复订单只有一次扣减。
追问：脚本执行成功但客户端超时，重试怎么办？
回答：在发送成功响应前注入延迟，让客户端以 50 毫秒超时重试；分别覆盖脚本执行前断连、执行后响应丢失、幂等记录过期，检查重试返回值和库存是否一致。
```

### Reference item_6fc0945c96303bd1e208

examples/materials/redis-answer.docx · paragraph:6 → paragraph:7

```text
问题：如何设计幂等键，避免重复扣库存？
回答：幂等键使用订单号并记录处理结果，重试时先返回原结果；库存键和幂等键使用同一个 hash tag 保证落在同一槽位。实验同时比较有幂等和无幂等的对照组，确认重复请求不会重复扣减。
```

## t2 · 上一答提到“核心是把读库存、判断库存和扣减放进同一个 Redis Lua 脚本，让其他请求无法插入这段读写过程”；结合秒杀库存服务，客户端在扣减成功后超时，重试怎样避免重复扣减？

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
- e4fec31a00ed11c: 11.079 — question terms: idempotency, stock; claim terms: lua, redis, stock

### Reasoning Basis

简历项目与能力：秒杀库存服务 / Redis Lua 并发库存扣减
源码依据：[e6098a5520314a3] stock.lua:1
源码依据：[ec796696445c541] service.py:1
源码依据：[e4fec31a00ed11c] README.md:1
参考方法：[item_6fc0945c96303bd1e208] 如何设计幂等键，避免重复扣库存？
参考方法：[item_d2587ee205a66af96880] Redis Lua 脚本为什么能防止库存超卖？
参考方法：[item_44c7f623f2af3e758c15] Redis 库存扣减遇到超时重试怎么处理？
工程细节与实验参数按问题场景推演；实验参数不表示已测得的结果。

### Inferred Design Details

实现上我会用 request_id 标识一次业务请求：脚本先检查幂等结果，再检查库存，最后完成扣减并保存结果；重复请求直接返回第一次的结果。参数类型和取值在写入前检查，库存 key 和幂等 key 在集群里使用同一个 hash tag。
具体处理时，我会采用这个流程：客户端超时不能证明服务端失败，重试沿用同一个订单号，先读已保存的处理结果。
具体处理时，我会采用这个流程：幂等键使用订单号并记录处理结果，重试时先返回原结果；库存键和幂等键使用同一个 hash tag 保证落在同一槽位。
具体处理时，我会采用这个流程：脚本先查幂等结果，再检查库存，最后完成扣减并保存结果；重复请求返回第一次的结果。

### Experiment Plan

实验上，我会这样安排：实验同时比较有幂等和无幂等的对照组，确认重复请求不会重复扣减。
性能实验把数据库条件更新作为基线，固定机器、连接池和请求分布，逐档增加并发，同时记录成功吞吐、拒绝率、P95/P99、Redis CPU 和连接等待时间，观察瓶颈出现在哪一档。

### Unsupported / Unverified

简历自述：设计 Redis + Lua 库存扣减，解决高并发下超卖问题，声称吞吐提升 40%。
源代码片段不能独立证明个人 Ownership、生产部署规模、性能提升比例或未展示的容错能力。
当前选取证据未包含相关测试或评测；实验方案与执行结果分别记录。
参考回答只提供方法和表达结构；其中的个人经历、部署规模与测量结果不归属于候选人。

### Reference item_593743c4abe06c46b3e6

examples/materials/interview.md · lines:5-7

```text
Q: Redis 库存扣减中，Lua 的原子性具体保护了哪些状态变化？
追问：客户端在扣减成功后超时，重试怎样避免重复扣减？
追问：脚本执行到一半出错时，已经执行的写入会发生什么？
```

### Reference item_6fc0945c96303bd1e208

examples/materials/redis-answer.docx · paragraph:6 → paragraph:7

```text
问题：如何设计幂等键，避免重复扣库存？
回答：幂等键使用订单号并记录处理结果，重试时先返回原结果；库存键和幂等键使用同一个 hash tag 保证落在同一槽位。实验同时比较有幂等和无幂等的对照组，确认重复请求不会重复扣减。
```

### Reference item_d2587ee205a66af96880

examples/materials/redis-answer.docx · paragraph:1 → paragraph:5

```text
问题：Redis Lua 脚本为什么能防止库存超卖？
回答：我把库存检查、幂等键检查和扣减放入同一段 Lua 脚本，以订单号作为业务幂等键。客户端超时不能证明服务端失败，重试沿用同一个订单号，先读已保存的处理结果。
实验设计：固定初始库存为 100，使用 200 个并发请求争抢，并让同一订单号重复发起 3 次。断言成功订单不超过 100，库存不为负，重复订单只有一次扣减。
追问：脚本执行成功但客户端超时，重试怎么办？
回答：在发送成功响应前注入延迟，让客户端以 50 毫秒超时重试；分别覆盖脚本执行前断连、执行后响应丢失、幂等记录过期，检查重试返回值和库存是否一致。
```

### Reference item_44c7f623f2af3e758c15

examples/materials/reference_answer.md · lines:3-4

```text
Q: Redis 库存扣减遇到超时重试怎么处理？
A: 我会让一次业务操作始终使用同一个 request_id。脚本先查幂等结果，再检查库存，最后完成扣减并保存结果；重复请求返回第一次的结果。库存 key 和幂等 key 在集群中使用相同的 hash tag。幂等记录的保留期覆盖客户端重试窗口，订单落库失败时进入有状态的补偿任务，补偿本身也按业务操作去重。这样能分别处理并发竞争、重复提交和跨资源部分成功。
```

## t3 · 上一答提到“超时后我首先按原 request_id 查询或重试，复用第一次处理结果”；结合秒杀库存服务，并发增加后吞吐不再增长，P99 却变高，怎么定位瓶颈？

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

- e6098a5520314a3: 24.431 — question terms: atomic, decrby, stock; claim terms: atomic, decrby, lua, redis, stock; artifact type relevant to question dimension
- ec796696445c541: 15.966 — question terms: reserve, stock; claim terms: lua, redis, reserve, stock; artifact type relevant to question dimension
- e4fec31a00ed11c: 6.0 — question terms: stock; claim terms: lua, redis, stock

### Reasoning Basis

简历项目与能力：秒杀库存服务 / Redis Lua 并发库存扣减
源码依据：[e6098a5520314a3] stock.lua:1
源码依据：[ec796696445c541] service.py:1
源码依据：[e4fec31a00ed11c] README.md:1
参考方法：[item_654f2e272a88deb685f4] 库存方案怎样做正确性和性能实验？
参考方法：[item_d2587ee205a66af96880] Redis Lua 脚本为什么能防止库存超卖？
参考方法：[item_6fc0945c96303bd1e208] 如何设计幂等键，避免重复扣库存？
工程细节与实验参数按问题场景推演；实验参数不表示已测得的结果。

### Inferred Design Details

实现上我会用 request_id 标识一次业务请求：脚本先检查幂等结果，再检查库存，最后完成扣减并保存结果；重复请求直接返回第一次的结果。参数类型和取值在写入前检查，库存 key 和幂等 key 在集群里使用同一个 hash tag。
具体处理时，我会采用这个流程：把库存检查、幂等键检查和扣减放入同一段 Lua 脚本，以订单号作为业务幂等键。
具体处理时，我会采用这个流程：幂等键使用订单号并记录处理结果，重试时先返回原结果；库存键和幂等键使用同一个 hash tag 保证落在同一槽位。
具体处理时，我会采用这个流程：把正确性检查与性能曲线一起看，才知道吞吐变化来自实现、负载还是资源瓶颈。

### Experiment Plan

实验上，我会这样安排：性能实验以数据库条件更新为对照，固定机器、连接池、数据规模和请求分布，逐档增加并发，同时记录成功吞吐、拒绝率、P95/P99、Redis CPU 和连接等待时间。
实验上，我会这样安排：性能实验以数据库条件更新为对照，固定机器、连接池、数据规模和请求分布，逐档增加并发，同时记录成功吞吐、拒绝率、P95/P99、Redis CPU 和连接等待时间。

### Unsupported / Unverified

简历自述：设计 Redis + Lua 库存扣减，解决高并发下超卖问题，声称吞吐提升 40%。
源代码片段不能独立证明个人 Ownership、生产部署规模、性能提升比例或未展示的容错能力。
当前选取证据未包含相关测试或评测；实验方案与执行结果分别记录。
参考回答只提供方法和表达结构；其中的个人经历、部署规模与测量结果不归属于候选人。

### Reference item_1b2a31afb6addcd3d425

examples/materials/interview.md · lines:12-13

```text
Q: 如果简历写吞吐提升，你会怎样设计可信的对照实验？
追问：并发增加后吞吐不再增长，P99 却变高，怎么定位瓶颈？
```

### Reference item_654f2e272a88deb685f4

examples/materials/reference_answer.md · lines:6-7

```text
Q: 库存方案怎样做正确性和性能实验？
A: 我会先设初始库存为 100，用 1,000 个不同请求并发争抢，验证成功扣减数等于 100、库存非负，并把成功结果与订单逐条对账。接着重复发送同一个 request_id，在扣减完成后断开连接，再注入订单写入失败，检查重试和补偿多次执行时业务效果仍然只有一次。性能实验以数据库条件更新为对照，固定机器、连接池、数据规模和请求分布，逐档增加并发，同时记录成功吞吐、拒绝率、P95/P99、Redis CPU 和连接等待时间。把正确性检查与性能曲线一起看，才知道吞吐变化来自实现、负载还是资源瓶颈。
```

### Reference item_d2587ee205a66af96880

examples/materials/redis-answer.docx · paragraph:1 → paragraph:5

```text
问题：Redis Lua 脚本为什么能防止库存超卖？
回答：我把库存检查、幂等键检查和扣减放入同一段 Lua 脚本，以订单号作为业务幂等键。客户端超时不能证明服务端失败，重试沿用同一个订单号，先读已保存的处理结果。
实验设计：固定初始库存为 100，使用 200 个并发请求争抢，并让同一订单号重复发起 3 次。断言成功订单不超过 100，库存不为负，重复订单只有一次扣减。
追问：脚本执行成功但客户端超时，重试怎么办？
回答：在发送成功响应前注入延迟，让客户端以 50 毫秒超时重试；分别覆盖脚本执行前断连、执行后响应丢失、幂等记录过期，检查重试返回值和库存是否一致。
```

### Reference item_6fc0945c96303bd1e208

examples/materials/redis-answer.docx · paragraph:6 → paragraph:7

```text
问题：如何设计幂等键，避免重复扣库存？
回答：幂等键使用订单号并记录处理结果，重试时先返回原结果；库存键和幂等键使用同一个 hash tag 保证落在同一槽位。实验同时比较有幂等和无幂等的对照组，确认重复请求不会重复扣减。
```

## t4 · 上一答提到“吞吐已经进入平台期，而 P99 继续升高，我首先怀疑请求在某个饱和资源前排队”；结合秒杀库存服务，数据库已经提交但连接断开时，客户端如何拿到最终结果？

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

### Reasoning Basis

简历项目与能力：秒杀库存服务 / Redis Lua 并发库存扣减
源码依据：[e6098a5520314a3] stock.lua:1
源码依据：[ec796696445c541] service.py:1
源码依据：[e4fec31a00ed11c] README.md:1
参考方法：[item_654f2e272a88deb685f4] 库存方案怎样做正确性和性能实验？
参考方法：[item_44c7f623f2af3e758c15] Redis 库存扣减遇到超时重试怎么处理？
参考方法：[item_d2587ee205a66af96880] Redis Lua 脚本为什么能防止库存超卖？
参考方法：[item_4036cfb76cc5ef6699b4] 如何设计有边界的服务重试？
工程细节与实验参数按问题场景推演；实验参数不表示已测得的结果。

### Inferred Design Details

实现上我会用 request_id 标识一次业务请求：脚本先检查幂等结果，再检查库存，最后完成扣减并保存结果；重复请求直接返回第一次的结果。参数类型和取值在写入前检查，库存 key 和幂等 key 在集群里使用同一个 hash tag。
具体处理时，我会采用这个流程：脚本先查幂等结果，再检查库存，最后完成扣减并保存结果；重复请求返回第一次的结果。
具体处理时，我会采用这个流程：客户端超时不能证明服务端失败，重试沿用同一个订单号，先读已保存的处理结果。
具体处理时，我会采用这个流程：写操作先明确业务唯一键，用数据库唯一约束把去重和写入放进同一个事务。

### Experiment Plan

实验上，我会这样安排：接着重复发送同一个 request_id，在扣减完成后断开连接，再注入订单写入失败，检查重试和补偿多次执行时业务效果仍然只有一次。
实验上，我会这样安排：接着重复发送同一个 request_id，在扣减完成后断开连接，再注入订单写入失败，检查重试和补偿多次执行时业务效果仍然只有一次。

### Unsupported / Unverified

简历自述：设计 Redis + Lua 库存扣减，解决高并发下超卖问题，声称吞吐提升 40%。
源代码片段不能独立证明个人 Ownership、生产部署规模、性能提升比例或未展示的容错能力。
当前选取证据未包含相关测试或评测；实验方案与执行结果分别记录。
参考回答只提供方法和表达结构；其中的个人经历、部署规模与测量结果不归属于候选人。

### Reference item_1b49c5af378fb1933297

examples/materials/interview.md · lines:22-23

```text
Q: 写请求遇到依赖超时，重试、幂等和事务边界怎样配合？
追问：数据库已经提交但连接断开时，客户端如何拿到最终结果？
```

### Reference item_654f2e272a88deb685f4

examples/materials/reference_answer.md · lines:6-7

```text
Q: 库存方案怎样做正确性和性能实验？
A: 我会先设初始库存为 100，用 1,000 个不同请求并发争抢，验证成功扣减数等于 100、库存非负，并把成功结果与订单逐条对账。接着重复发送同一个 request_id，在扣减完成后断开连接，再注入订单写入失败，检查重试和补偿多次执行时业务效果仍然只有一次。性能实验以数据库条件更新为对照，固定机器、连接池、数据规模和请求分布，逐档增加并发，同时记录成功吞吐、拒绝率、P95/P99、Redis CPU 和连接等待时间。把正确性检查与性能曲线一起看，才知道吞吐变化来自实现、负载还是资源瓶颈。
```

### Reference item_44c7f623f2af3e758c15

examples/materials/reference_answer.md · lines:3-4

```text
Q: Redis 库存扣减遇到超时重试怎么处理？
A: 我会让一次业务操作始终使用同一个 request_id。脚本先查幂等结果，再检查库存，最后完成扣减并保存结果；重复请求返回第一次的结果。库存 key 和幂等 key 在集群中使用相同的 hash tag。幂等记录的保留期覆盖客户端重试窗口，订单落库失败时进入有状态的补偿任务，补偿本身也按业务操作去重。这样能分别处理并发竞争、重复提交和跨资源部分成功。
```

### Reference item_d2587ee205a66af96880

examples/materials/redis-answer.docx · paragraph:1 → paragraph:5

```text
问题：Redis Lua 脚本为什么能防止库存超卖？
回答：我把库存检查、幂等键检查和扣减放入同一段 Lua 脚本，以订单号作为业务幂等键。客户端超时不能证明服务端失败，重试沿用同一个订单号，先读已保存的处理结果。
实验设计：固定初始库存为 100，使用 200 个并发请求争抢，并让同一订单号重复发起 3 次。断言成功订单不超过 100，库存不为负，重复订单只有一次扣减。
追问：脚本执行成功但客户端超时，重试怎么办？
回答：在发送成功响应前注入延迟，让客户端以 50 毫秒超时重试；分别覆盖脚本执行前断连、执行后响应丢失、幂等记录过期，检查重试返回值和库存是否一致。
```

### Reference item_4036cfb76cc5ef6699b4

examples/materials/reference_answer.md · lines:12-13

```text
Q: 如何设计有边界的服务重试？
A: 我会给请求传递统一 deadline，对每个依赖设置超时和并发上限；只重试可恢复错误，使用有限次数、退避和抖动。写操作先明确业务唯一键，用数据库唯一约束把去重和写入放进同一个事务。连接断开时客户端按操作 ID 查询状态，避免把超时等同于操作失败。验证时覆盖重复提交、提交后断连和慢依赖，观察数据一致性、连接池等待、额外请求放大量及恢复时间。
```

## t5 · 上一答提到“数据库已经提交时，连接断开只影响结果送达”；结合秒杀库存服务，补偿任务重复执行会不会多加库存？

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

### Reasoning Basis

简历项目与能力：秒杀库存服务 / Redis Lua 并发库存扣减
源码依据：[e6098a5520314a3] stock.lua:1
源码依据：[ec796696445c541] service.py:1
源码依据：[e4fec31a00ed11c] README.md:1
参考方法：[item_d2587ee205a66af96880] Redis Lua 脚本为什么能防止库存超卖？
参考方法：[item_44c7f623f2af3e758c15] Redis 库存扣减遇到超时重试怎么处理？
工程细节与实验参数按问题场景推演；实验参数不表示已测得的结果。

### Inferred Design Details

实现上我会用 request_id 标识一次业务请求：脚本先检查幂等结果，再检查库存，最后完成扣减并保存结果；重复请求直接返回第一次的结果。参数类型和取值在写入前检查，库存 key 和幂等 key 在集群里使用同一个 hash tag。
具体处理时，我会采用这个流程：脚本先查幂等结果，再检查库存，最后完成扣减并保存结果；重复请求返回第一次的结果。
对账任务我会按业务请求 ID 比较预扣、订单和补偿状态，只重放缺失的状态迁移，并保留重试次数和人工处理入口。
具体处理时，我会采用这个流程：客户端超时不能证明服务端失败，重试沿用同一个订单号，先读已保存的处理结果。

### Experiment Plan

实验上，我会这样安排：固定初始库存为 100，使用 200 个并发请求争抢，并让同一订单号重复发起 3 次。
验证时，我会检查：成功订单不超过 100，库存不为负，重复订单只有一次扣减。
实验上，我会这样安排：在发送成功响应前注入延迟，让客户端以 50 毫秒超时重试；分别覆盖脚本执行前断连、执行后响应丢失、幂等记录过期，检查重试返回值和库存是否一致。
性能实验把数据库条件更新作为基线，固定机器、连接池和请求分布，逐档增加并发，同时记录成功吞吐、拒绝率、P95/P99、Redis CPU 和连接等待时间，观察瓶颈出现在哪一档。

### Unsupported / Unverified

简历自述：设计 Redis + Lua 库存扣减，解决高并发下超卖问题，声称吞吐提升 40%。
源代码片段不能独立证明个人 Ownership、生产部署规模、性能提升比例或未展示的容错能力。
当前选取证据未包含相关测试或评测；实验方案与执行结果分别记录。
参考回答只提供方法和表达结构；其中的个人经历、部署规模与测量结果不归属于候选人。

### Reference item_76d0b0e7523a69902903

examples/materials/interview.md · lines:9-10

```text
Q: 订单写入失败时，库存扣减和补偿应该如何协调？
追问：补偿任务重复执行会不会多加库存？
```

### Reference item_d2587ee205a66af96880

examples/materials/redis-answer.docx · paragraph:1 → paragraph:5

```text
问题：Redis Lua 脚本为什么能防止库存超卖？
回答：我把库存检查、幂等键检查和扣减放入同一段 Lua 脚本，以订单号作为业务幂等键。客户端超时不能证明服务端失败，重试沿用同一个订单号，先读已保存的处理结果。
实验设计：固定初始库存为 100，使用 200 个并发请求争抢，并让同一订单号重复发起 3 次。断言成功订单不超过 100，库存不为负，重复订单只有一次扣减。
追问：脚本执行成功但客户端超时，重试怎么办？
回答：在发送成功响应前注入延迟，让客户端以 50 毫秒超时重试；分别覆盖脚本执行前断连、执行后响应丢失、幂等记录过期，检查重试返回值和库存是否一致。
```

### Reference item_44c7f623f2af3e758c15

examples/materials/reference_answer.md · lines:3-4

```text
Q: Redis 库存扣减遇到超时重试怎么处理？
A: 我会让一次业务操作始终使用同一个 request_id。脚本先查幂等结果，再检查库存，最后完成扣减并保存结果；重复请求返回第一次的结果。库存 key 和幂等 key 在集群中使用相同的 hash tag。幂等记录的保留期覆盖客户端重试窗口，订单落库失败时进入有状态的补偿任务，补偿本身也按业务操作去重。这样能分别处理并发竞争、重复提交和跨资源部分成功。
```

## t6 · 上一答提到“补偿本身也要幂等”；结合秒杀库存服务，如果简历写吞吐提升，你会怎样设计可信的对照实验？

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

- e6098a5520314a3: 14.466 — question terms: decrby, stock; claim terms: atomic, decrby, lua, redis, stock
- ec796696445c541: 12.773 — question terms: reserve, stock; claim terms: lua, redis, reserve, stock
- e4fec31a00ed11c: 6.0 — question terms: stock; claim terms: lua, redis, stock

### Reasoning Basis

简历项目与能力：秒杀库存服务 / Redis Lua 并发库存扣减
源码依据：[e6098a5520314a3] stock.lua:1
源码依据：[ec796696445c541] service.py:1
源码依据：[e4fec31a00ed11c] README.md:1
参考方法：[item_654f2e272a88deb685f4] 库存方案怎样做正确性和性能实验？
参考方法：[item_6fc0945c96303bd1e208] 如何设计幂等键，避免重复扣库存？
参考方法：[item_d2587ee205a66af96880] Redis Lua 脚本为什么能防止库存超卖？
工程细节与实验参数按问题场景推演；实验参数不表示已测得的结果。

### Inferred Design Details

实现上我会用 request_id 标识一次业务请求：脚本先检查幂等结果，再检查库存，最后完成扣减并保存结果；重复请求直接返回第一次的结果。参数类型和取值在写入前检查，库存 key 和幂等 key 在集群里使用同一个 hash tag。
具体处理时，我会采用这个流程：幂等键使用订单号并记录处理结果，重试时先返回原结果；库存键和幂等键使用同一个 hash tag 保证落在同一槽位。
具体处理时，我会采用这个流程：把库存检查、幂等键检查和扣减放入同一段 Lua 脚本，以订单号作为业务幂等键。
具体处理时，我会采用这个流程：把正确性检查与性能曲线一起看，才知道吞吐变化来自实现、负载还是资源瓶颈。

### Experiment Plan

实验上，我会这样安排：先设初始库存为 100，用 1,000 个不同请求并发争抢，验证成功扣减数等于 100、库存非负，并把成功结果与订单逐条对账。
实验上，我会这样安排：接着重复发送同一个 request_id，在扣减完成后断开连接，再注入订单写入失败，检查重试和补偿多次执行时业务效果仍然只有一次。
实验上，我会这样安排：性能实验以数据库条件更新为对照，固定机器、连接池、数据规模和请求分布，逐档增加并发，同时记录成功吞吐、拒绝率、P95/P99、Redis CPU 和连接等待时间。

### Unsupported / Unverified

简历自述：设计 Redis + Lua 库存扣减，解决高并发下超卖问题，声称吞吐提升 40%。
源代码片段不能独立证明个人 Ownership、生产部署规模、性能提升比例或未展示的容错能力。
当前选取证据未包含相关测试或评测；实验方案与执行结果分别记录。
参考回答只提供方法和表达结构；其中的个人经历、部署规模与测量结果不归属于候选人。

### Reference item_1b2a31afb6addcd3d425

examples/materials/interview.md · lines:12-13

```text
Q: 如果简历写吞吐提升，你会怎样设计可信的对照实验？
追问：并发增加后吞吐不再增长，P99 却变高，怎么定位瓶颈？
```

### Reference item_654f2e272a88deb685f4

examples/materials/reference_answer.md · lines:6-7

```text
Q: 库存方案怎样做正确性和性能实验？
A: 我会先设初始库存为 100，用 1,000 个不同请求并发争抢，验证成功扣减数等于 100、库存非负，并把成功结果与订单逐条对账。接着重复发送同一个 request_id，在扣减完成后断开连接，再注入订单写入失败，检查重试和补偿多次执行时业务效果仍然只有一次。性能实验以数据库条件更新为对照，固定机器、连接池、数据规模和请求分布，逐档增加并发，同时记录成功吞吐、拒绝率、P95/P99、Redis CPU 和连接等待时间。把正确性检查与性能曲线一起看，才知道吞吐变化来自实现、负载还是资源瓶颈。
```

### Reference item_6fc0945c96303bd1e208

examples/materials/redis-answer.docx · paragraph:6 → paragraph:7

```text
问题：如何设计幂等键，避免重复扣库存？
回答：幂等键使用订单号并记录处理结果，重试时先返回原结果；库存键和幂等键使用同一个 hash tag 保证落在同一槽位。实验同时比较有幂等和无幂等的对照组，确认重复请求不会重复扣减。
```

### Reference item_d2587ee205a66af96880

examples/materials/redis-answer.docx · paragraph:1 → paragraph:5

```text
问题：Redis Lua 脚本为什么能防止库存超卖？
回答：我把库存检查、幂等键检查和扣减放入同一段 Lua 脚本，以订单号作为业务幂等键。客户端超时不能证明服务端失败，重试沿用同一个订单号，先读已保存的处理结果。
实验设计：固定初始库存为 100，使用 200 个并发请求争抢，并让同一订单号重复发起 3 次。断言成功订单不超过 100，库存不为负，重复订单只有一次扣减。
追问：脚本执行成功但客户端超时，重试怎么办？
回答：在发送成功响应前注入延迟，让客户端以 50 毫秒超时重试；分别覆盖脚本执行前断连、执行后响应丢失、幂等记录过期，检查重试返回值和库存是否一致。
```
