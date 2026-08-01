"""
Galaxy Gamez - Text styling helper
Converts plain ASCII into Mathematical Bold unicode so every bot message
uses the SAME font style consistently (matches the post caption design).
"""

_UPPER_START = ord("A")
_LOWER_START = ord("a")
_DIGIT_START = ord("0")

_BOLD_UPPER = 0x1D400
_BOLD_LOWER = 0x1D41A
_BOLD_DIGIT = 0x1D7CE


def bold(text):
    """Mathematical Bold (serif) - matches 'GAME NAME' / 'PASSWORD' style."""
    out = []
    for ch in text:
        if "A" <= ch <= "Z":
            out.append(chr(_BOLD_UPPER + (ord(ch) - _UPPER_START)))
        elif "a" <= ch <= "z":
            out.append(chr(_BOLD_LOWER + (ord(ch) - _LOWER_START)))
        elif "0" <= ch <= "9":
            out.append(chr(_BOLD_DIGIT + (ord(ch) - _DIGIT_START)))
        else:
            out.append(ch)
    return "".join(out)


def box(title):
    """Small boxed header, matches the POWERED BY footer style."""
    return f"┏━━━━━━━━━━━━━━━┓\n   {bold(title)}\n┗━━━━━━━━━━━━━━━┛"


def credits_block(handle):
    return f"{box('CREDITS')}\n👉 {handle}"
