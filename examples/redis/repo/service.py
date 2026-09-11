"""Illustrative caller; requires a caller-supplied Redis connection."""
from pathlib import Path


def reserve(redis_client, sku: str, amount: int):
    lua = Path(__file__).with_name("stock.lua").read_text()
    return redis_client.eval(lua, 1, "stock:" + sku, amount)
