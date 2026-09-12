"""Untrusted text never controls the terminal.

Model content, reasoning, task text, commitment text, resource values, review notes and provider errors are all
untrusted display strings. Every one of them passes through `display()` before it reaches a screen, a log line or
a snapshot: C0 and C1 control characters (ESC, BEL, CSI/OSC/DCS introducers, ...) and DEL become their visible
Unicode control pictures, ordinary text and deliberate newlines/tabs are kept, and the result is length-bounded.
Once ESC is a picture, an escape sequence is just characters: no OSC 52 clipboard write, no title change, no
screen clear, no hyperlink, no cursor movement can come from data.
"""
from __future__ import annotations

# U+2400.. are the "control pictures"; DEL has its own picture at U+2421.
_C0 = {i: chr(0x2400 + i) for i in range(0x20)}
_C0[0x7F] = "␡"
# C1 controls (U+0080..U+009F) include the 8-bit CSI (0x9B), OSC (0x9D), DCS (0x90) and ST (0x9C) introducers.
_C1 = {i: f"␀{i - 0x80:02X}" for i in range(0x80, 0xA0)}
_KEEP = {0x0A: "\n", 0x09: "\t"}
_TABLE = {**_C0, **_C1, **_KEEP}
# Line/paragraph separators can break single-line table cells; zero-width and bidi controls can hide or reorder
# what the operator reads. They are made visible too.
_TABLE.update({0x2028: "␤", 0x2029: "␤", 0x200B: "␀", 0x200C: "␀", 0x200D: "␀",
               0x200E: "␀", 0x200F: "␀", 0x202A: "␀", 0x202B: "␀", 0x202C: "␀",
               0x202D: "␀", 0x202E: "␀", 0x2066: "␀", 0x2067: "␀", 0x2068: "␀",
               0x2069: "␀", 0xFEFF: "␀"})

TRUNCATED = " …[truncated]"


def display(value: object, *, max_chars: int = 4000, one_line: bool = False) -> str:
    """Render any value as terminal-safe text. Non-strings are shown through `str()` and sanitized the same way."""
    text = value if isinstance(value, str) else str(value)
    text = text.translate(_TABLE)
    if one_line:
        text = text.replace("\n", "␤").replace("\t", "␉")
    if len(text) > max_chars:
        text = text[: max(0, max_chars - len(TRUNCATED))] + TRUNCATED
    return text


def is_clean(text: str) -> bool:
    """True when `text` contains nothing the sanitizer would change (used by the tests and the log writer)."""
    return text == text.translate(_TABLE)
