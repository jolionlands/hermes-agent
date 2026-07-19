from __future__ import annotations

import sys


def test_title_denylist_resolves_per_board_override():
    from gateway.kanban_watchers import _resolve_dispatch_title_denylist

    assert _resolve_dispatch_title_denylist(
        ["GLOBAL"],
        {"library": ["HUMAN/OPS", "human/ops"]},
        "library",
        lambda value: value.lower(),
    ) == ["human/ops"]


def test_title_denylist_keeps_manual_cards_ready(monkeypatch, tmp_path):
    home = tmp_path / "hermes"
    (home / "profiles" / "library").mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(home))
    for name in list(sys.modules):
        if name.startswith(("hermes_cli", "hermes_state")):
            sys.modules.pop(name)

    from hermes_cli import kanban_db as kb

    with kb.connect_closing() as conn:
        kb.create_board(slug="library", name="Library")
        manual = kb.create_task(
            conn,
            title="HUMAN/OPS: archive cards",
            assignee="library",
        )
        normal = kb.create_task(
            conn,
            title="Review catalog metadata",
            assignee="library",
        )
    with kb.connect_closing() as conn:
        result = kb.dispatch_once(
            conn,
            dry_run=True,
            spawn_fn=lambda *_args, **_kwargs: 123,
            title_denylist=["HUMAN/OPS"],
            board="library",
        )

    assert result.skipped_title_denylist == [(manual, "human/ops")]
    assert {task_id for task_id, *_ in result.spawned} == {normal}
