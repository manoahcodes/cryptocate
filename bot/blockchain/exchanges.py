"""
Exchange address classifier — maps known hot wallet addresses to exchange labels.

Used to label inflows/outflows on all alert messages (free + pro).
"""

# Known exchange deposit/hot wallet addresses (lowercase)
# These are publicly known addresses from on-chain analysis
EXCHANGE_LABELS: dict[str, str] = {
    # Binance
    "0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be": "Binance",
    "0xd551234ae421e3bcba99a0da6d736074f22192ff": "Binance",
    "0x564286362092d8e7936f0549571a803b203aaced": "Binance",
    "0x0681d8db095565fe8a346fa0277bffde9c0edbbf": "Binance",
    "0xfe9e8709d3215310075d67e3ed32a380ccf451c8": "Binance",
    "0x4e9ce36e442e55ecd9025b9a6e0d88485d628a67": "Binance",
    # Coinbase
    "0x71660c4005ba85c37ccec55d0c4493e66fe775d3": "Coinbase",
    "0x503828976d22510aad0201ac7ec88293211d23da": "Coinbase",
    "0xddfabcdc4d8ffc6d5beaf154f18b778f892a0740": "Coinbase",
    "0x3cd751e6b0078be393132286c442345e5dc49699": "Coinbase",
    "0xb5d85cbf7cb3ee0d56b3bb207d5fc4b82f43f511": "Coinbase",
    "0xa090e606e30bd747d4e6245a1517ebe430f0057e": "Coinbase",
    # Kraken
    "0x2910543af39aba0cd09dbb2d50200b3e800a63d2": "Kraken",
    "0x0a869d79a7052c7f1b55a8ebabbea3420f0d1e13": "Kraken",
    "0xe853c56864a2ebe4576a807d26fdc4a0ada51919": "Kraken",
    "0x267be1c1d684f78cb4f6a176c4911b741e4ffdc0": "Kraken",
    # OKX
    "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b": "OKX",
    "0x98ec059dc3adfbdd63429454aeb0c990fba4a128": "OKX",
    "0x236f9f97e0e62388479bf9e5ba4889e46b0273c3": "OKX",
    # Bybit
    "0xf89d7b9c864f589bbf53a82105107622b35eaa40": "Bybit",
    "0x1ab4973a48dc892cd9971ece8e01dcc7688f8f23": "Bybit",
    # Huobi / HTX
    "0xab5c66752a9e8167967685f1450532fb96d5d24f": "Huobi",
    "0x6748f50f686bfbca6fe8ad62b22228b87f31ff2b": "Huobi",
    "0xfdb16996831753d5331ff813c29a93c76834a0ad": "Huobi",
    # Gate.io
    "0x0d0707963952f2fba59dd06f2b425ace40b492fe": "Gate.io",
    "0x7793cd85c11a924478d358d49b05b37e91b5810f": "Gate.io",
    # KuCoin
    "0x2b5634c42055806a59e9107ed44d43c426e58258": "KuCoin",
    "0xa1d8d972560c2f8144af871db508f0b0b10a3fbf": "KuCoin",
    # Bitfinex
    "0x742d35cc6634c0532925a3b844bc454e4438f44e": "Bitfinex",
    "0x876eabf441b2ee5b5b0554fd502a8e0600950cfa": "Bitfinex",
    # Gemini
    "0xd24400ae8bfebb18ca49be86258a3c749cf46853": "Gemini",
    "0x07ee55aa48bb72dcc6e9d78256648910de513eca": "Gemini",
    # Crypto.com
    "0x46340b20830761efd32832a74d7169b29feb9758": "Crypto.com",
    "0xcffad3200574698b78f32232aa9d63eabd290703": "Crypto.com",
    # Uniswap (DEX routers)
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": "Uniswap v2",
    "0xe592427a0aece92de3edee1f18e0157c05861564": "Uniswap v3",
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": "Uniswap v3",
}


def get_exchange_label(address: str) -> str:
    """
    Return the exchange label for a known address, or empty string.
    Case-insensitive lookup.
    """
    if not address:
        return ""
    return EXCHANGE_LABELS.get(address.lower(), "")


def classify_transfer(
    from_address: str, to_address: str
) -> tuple[str, str]:
    """
    Classify a transfer as an exchange inflow or outflow.

    Returns:
        (direction, exchange_label)
        direction: "inflow" | "outflow" | ""
        exchange_label: e.g. "Binance" or ""
    """
    from_label = get_exchange_label(from_address)
    to_label = get_exchange_label(to_address)

    if to_label:
        # Sending TO an exchange = deposit / outflow from wallet perspective
        return "outflow", to_label
    if from_label:
        # Receiving FROM an exchange = withdrawal / inflow to wallet
        return "inflow", from_label

    return "", ""
