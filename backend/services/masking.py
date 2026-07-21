"""API key masking utilities."""


def mask_api_key(key: str) -> str:
    """
    Shows only the last 4 characters, masks the rest with asterisks.
    For keys shorter than 5 chars, mask all but last char.
    Empty string returns empty string.
    Single char returns "*".
    """
    if not key:
        return ""
    if len(key) == 1:
        return "*"
    if len(key) <= 4:
        return "*" * (len(key) - 1) + key[-1:]
    return "*" * (len(key) - 4) + key[-4:]
