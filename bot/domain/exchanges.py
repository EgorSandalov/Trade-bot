SUPPORTED_EXCHANGES = (
    "OKX",
    "BINANCE",
    "BYBIT",
    "BITGET",
    "BINGX",
    "MEXC",
    "HYPERLIQUID",
)

EXCHANGE_ALIASES: dict[str, str] = {
    "HL": "HYPERLIQUID",
    "HYPERLIQUID": "HYPERLIQUID",
    "HYPE": "HYPERLIQUID",
    "MEX": "MEXC",
    "MEXC": "MEXC",
}


def normalize_exchange(name: str) -> str:
    key = name.upper().strip()
    return EXCHANGE_ALIASES.get(key, key)


def is_supported_exchange(name: str) -> bool:
    return normalize_exchange(name) in SUPPORTED_EXCHANGES


def exchanges_list() -> str:
    return ", ".join(SUPPORTED_EXCHANGES)
