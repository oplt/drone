from __future__ import annotations


def parse_delimited_tokens(value: str) -> list[str]:
    """Parse comma, semicolon, or whitespace separated tokens in stable order."""
    tokens = value.replace(";", ",").replace(" ", ",").split(",") if value else []
    return list(dict.fromkeys(token.strip() for token in tokens if token.strip()))
