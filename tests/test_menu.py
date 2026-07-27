"""Unit tests for the selection-menu ordering (most-recently-played first)."""

import importlib.util
import json
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def cli():
    """Import anki-cli.py (hyphenated, not a normal module) for direct testing."""
    spec = importlib.util.spec_from_file_location(
        "anki_cli_main", os.path.join(ROOT, "anki-cli.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _play(memory_dir, key, mtime):
    """Write a minimal state file for `key` and stamp it as last played at mtime."""
    path = os.path.join(memory_dir, f"{key}.json")
    with open(path, "w") as f:
        json.dump({"cardset_id": key, "cards": {}, "total_cards": 1}, f)
    os.utime(path, (mtime, mtime))


def test_menu_order_most_recently_played_first(cli, tmp_path):
    options = [("a", "A"), ("b", "B"), ("c", "C"), ("d", "D")]
    _play(tmp_path, "a", 100.0)
    _play(tmp_path, "b", 300.0)
    _play(tmp_path, "c", 200.0)
    # d never played
    order = [k for k, _ in cli._menu_order(options, str(tmp_path))]
    assert order == ["b", "c", "a", "d"]   # played by recency desc, then unplayed


def test_menu_order_unplayed_keep_canonical_order(cli, tmp_path):
    options = [("a", "A"), ("b", "B"), ("c", "C")]
    order = [k for k, _ in cli._menu_order(options, str(tmp_path))]
    assert order == ["a", "b", "c"]        # new user: default order preserved


def test_menu_order_played_beats_unplayed(cli, tmp_path):
    options = [("a", "A"), ("b", "B"), ("c", "C")]
    _play(tmp_path, "c", 50.0)             # only c played, and it's last canonically
    order = [k for k, _ in cli._menu_order(options, str(tmp_path))]
    assert order[0] == "c"                 # any played set outranks unplayed ones
    assert order[1:] == ["a", "b"]


def test_last_played_none_when_never_played(cli, tmp_path):
    assert cli._last_played("nope", str(tmp_path)) is None
