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
