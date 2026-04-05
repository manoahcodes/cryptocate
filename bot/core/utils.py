"""
Shared utilities for WhaleWatch bot messaging.
"""

import re


def escape_md(text: str) -> str:
    """
    Escape all MarkdownV2 special characters in a plain-text string.

    Use this whenever inserting dynamic values (usernames, addresses,
    amounts, emails, numbers etc.) into a MarkdownV2-formatted message.

    MarkdownV2 special characters that must be escaped:
      _ * [ ] ( ) ~ ` > # + - = | { } . !

    Reference: https://core.telegram.org/bots/api#markdownv2-style

    Example:
        msg = f"Balance: *{escape_md(f'{amount:.4f}')} ETH*"
        # -> "Balance: *1\\.2340 ETH*"  <- safe for MarkdownV2
    """
    # Use a lambda to avoid regex backreference ambiguity
    return re.sub(
        r'([_*\[\]()~`>#+=|{}.!-])',
        lambda m: "\\" + m.group(1),
        str(text),
    )