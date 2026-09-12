# Repository Evidence Map



Bounded static scan; omitted or unmatched code remains unverified.

Data Flow requires semantic inspection; file categories are search hints, not confirmed architecture.

Possible credentials are filtered heuristically; review inputs before using a remote provider.

## e4fec31a00ed11c: README.md:1-6

Claims: c2, c3, c5, c1, c4, c6, c8, c7 · documentation · sha256: c6e198fa1396b53344ca9e5a40a109222f821104779b0a489fb9f00014811acb

```text
# Stock fixture

Redis Lua performs a stock check and decrement. This fixture is intentionally incomplete:
no idempotency key, order database, production deployment or benchmark. The resume's 40%
improvement is a deliberately unsupported claim for InterviewForge's evidence-boundary eval.
Do not execute this fixture as a production service.
```

Static source observation; not runtime verification, ownership or measured improvement.

## ec796696445c541: service.py:1-7

Claims: c2, c3, c5, c1, c4, c6, c8, c7 · implementation · sha256: 40e15391447f3736387c8671b63af61deb2938b48e501ffed0dbdd089753dbcb

```text
"""Illustrative caller; requires a caller-supplied Redis connection."""
from pathlib import Path


def reserve(redis_client, sku: str, amount: int):
    lua = Path(__file__).with_name("stock.lua").read_text()
    return redis_client.eval(lua, 1, "stock:" + sku, amount)
```

Static source observation; not runtime verification, ownership or measured improvement.

## e6098a5520314a3: stock.lua:1-11

Claims: c2, c3, c5, c1, c4, c6, c8, c7 · implementation · sha256: 0cc9efe91507c35f5c9479dde48a7da3a12993b44cc20e03e7e93e6f2118cc21

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

Static source observation; not runtime verification, ownership or measured improvement.
