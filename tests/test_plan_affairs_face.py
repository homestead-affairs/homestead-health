"""X7-drift-health — `docs/PLAN-affairs-face.md` may only strike a bite
through once it has actually merged, and the proof that it merged is a PR
number sitting right there in the text. A strikethrough with no `#NN` beside
it is exactly the wishful "surely this landed" this file exists to forbid.
"""
from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
PLAN_FACE = APP / "docs" / "PLAN-affairs-face.md"

_STRIKE_RE = re.compile(r"~~(.*?)~~", re.DOTALL)
_PR_RE = re.compile(r"#\d+")

#: How far past a `~~...~~` span to look for its `(#NN, released ...)` tail —
#: generous enough for this file's longest struck bite's trailing note,
#: narrow enough that one bite's PR number cannot satisfy the *next* bite's
#: strikethrough by accident.
_TAIL_WINDOW = 200


def _struck_blocks(text: str) -> list[tuple[str, str]]:
    """Every `~~...~~` span, paired with the text right after it — where this
    file's own convention puts `(#NN, released X.Y.Z — "...")`."""
    return [
        (m.group(1), text[m.end():m.end() + _TAIL_WINDOW])
        for m in _STRIKE_RE.finditer(text)
    ]


def test_every_struck_bite_names_a_pr_number():
    """The house rule, run for real: a strikethrough without a PR number
    right after it is not proof anything merged."""
    text = PLAN_FACE.read_text(encoding="utf-8")
    blocks = _struck_blocks(text)
    assert blocks, "docs/PLAN-affairs-face.md has no struck-through bites yet"
    missing = [
        struck.strip()[:60] for struck, tail in blocks if not _PR_RE.search(tail)
    ]
    assert not missing, (
        "these struck-through bites in docs/PLAN-affairs-face.md name no PR "
        f"number in the text right after the strikethrough: {missing}"
    )


def test_the_pr_number_guard_fires_on_a_planted_strikethrough_with_no_pr():
    """A scan that has never fired has not been shown to check anything: a
    struck bite missing its PR number must be named."""
    planted = "~~a bite claimed landed~~ (released 9.9.9, but the PR number was forgotten)\n"
    blocks = _struck_blocks(planted)
    assert blocks, "the plant must contain a strikethrough span"
    struck, tail = blocks[0]
    assert not _PR_RE.search(tail), "the guard fires only when no #NN follows"
