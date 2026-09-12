"""Untrusted text never controls the terminal (docs/design/peb_cockpit_tui_design.md's hard acceptance test, kept)."""
from __future__ import annotations

from peb.tui.sanitize import TRUNCATED, display, is_clean


def test_the_designs_adversarial_string_becomes_visible_text():
    hostile = "\x1b]52;c;BASE64SECRET\x07\x1b[2Jfake verified"
    shown = display(hostile)
    assert shown == "␛]52;c;BASE64SECRET␇␛[2Jfake verified"
    assert "\x1b" not in shown and "\x07" not in shown and is_clean(shown)


def test_every_c0_c1_and_del_control_is_made_visible_and_text_is_kept():
    for code in list(range(0x20)) + [0x7F] + list(range(0x80, 0xA0)):
        if code in (0x0A, 0x09):
            continue
        shown = display(f"a{chr(code)}b")
        assert chr(code) not in shown and shown.startswith("a") and shown.endswith("b") and len(shown) > 2
    assert display("plain ünïcödé 日本語 ✓") == "plain ünïcödé 日本語 ✓"
    assert display("line1\nline2\tcol") == "line1\nline2\tcol"
    assert display("line1\nline2\tcol", one_line=True) == "line1␤line2␉col"


def test_8bit_csi_osc_dcs_and_hidden_unicode_controls_cannot_pass():
    hostiles = ["\x9b2J", "\x9d52;c;x\x9c", "\x90q\x9c", "a\u200bb", "\u202eevil", "x\u2028y", "\ufeffbom"]
    for hostile in hostiles:
        shown = display(hostile)
        assert is_clean(shown) and shown != hostile
        assert all(ord(ch) not in range(0x80, 0xA0) and ord(ch) not in (0x200B, 0x202E, 0x2028, 0xFEFF) for ch in shown)


def test_output_is_bounded_and_non_strings_are_sanitized_too():
    long = "x" * 10_000
    shown = display(long, max_chars=100)
    assert len(shown) == 100 and shown.endswith(TRUNCATED)

    class Loud:
        def __str__(self) -> str:
            return "\x1b[31mred"

    assert display(Loud()) == "␛[31mred" and is_clean(display({"k": "\x1b[31mred"}))  # str() of a dict already escapes
    assert display(None) == "None" and display(3) == "3"
