"""Locale-tolerant number parsing for prices and percents."""


def parse_number(text: str) -> float:
    """Parse ``96000``, ``96,000``, ``0,5``, ``1.5``, ``10,50``."""
    text = text.strip().replace("$", "").replace(" ", "")
    if not text:
        raise ValueError("empty number")

    comma_count = text.count(",")
    dot_count = text.count(".")

    if comma_count and dot_count:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif comma_count == 1:
        before, after = text.split(",", 1)
        if (
            after.isdigit()
            and len(after) == 3
            and before.isdigit()
            and int(before) > 0
        ):
            text = before + after
        else:
            text = f"{before}.{after}"
    elif comma_count > 1:
        text = text.replace(",", "")

    return float(text)
