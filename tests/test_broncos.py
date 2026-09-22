"""Unit tests for the broncos set: wikitext parsing, roster semantics, rendering,
cards, new-card order, and the scheduler's reset-on-changed-answer."""

import re
from datetime import datetime

import pytest

from broncos.AcBroncosCardSet import AcBroncosCardSet
from broncos.AcBroncosData import (
    infobox_field, is_stale, most_recent_tuesday, parse_staff, parse_stints,
    parse_wiki_draft, stripe_rows,
)
from broncos.AcBroncosRoster import render_table, short_name, _Cell
from cards.lineLayout import justify, vis_len
from cards.ordering import batched_variant_order, chunk_evenly
from cards.textMatch import person_name_match
from memory.AcReviewStore import AcReviewStore
from memory.AcScheduler import AcScheduler
from fsrs import Rating

_ANSI = re.compile(r"\033\[[0-9;]*m")


def _plain(s: str) -> str:
    return _ANSI.sub("", s)


def _stint(team, start, end, league="NFL"):
    return {"team": team, "league": league, "start": start, "end": end}


def _player(pid, name, jersey, stints, draft=None, wiki_draft=None, status="", salary=None):
    return {"id": pid, "kind": "player", "name": name, "jersey": jersey, "status": status,
            "salary": salary, "draft": draft or {}, "wiki_draft": wiki_draft or {}, "stints": stints}


def _snapshot():
    den = lambda y: [_stint("DEN", y, None)]
    people = [
        _player("1", "Bo Nix", "10", den(2024), {"year": 2024, "round": 1, "pick": 12, "team": "DEN"}, salary=2487106),
        _player("2", "Jarrett Stidham", "8", [_stint("NE", 2019, 2021), _stint("LV", 2022, 2022), _stint("DEN", 2023, None)],
                {"year": 2019, "round": 4, "pick": 133, "team": "NE"}, salary=6500000),
        _player("3", "Jaylen Waddle", "17", [_stint("MIA", 2021, 2025), _stint("DEN", 2026, None)],
                {"year": 2021, "round": 1, "pick": 6, "team": "MIA"}, salary=17241000),
        _player("4", "Courtland Sutton", "14", den(2018), {"year": 2018, "round": 2, "pick": 40, "team": "DEN"}),
        _player("5", "Marvin Mims Jr.", "19", den(2023), {"year": 2023, "round": 2, "pick": 63, "team": "DEN"}, status="O"),
        _player("6", "Pat Bryant", "13", den(2025), {"year": 2025, "round": 3, "pick": 74, "team": "DEN"}),
        _player("7", "Lil'Jordan Humphrey", "5",
                [_stint("NO", 2019, 2021), _stint("DEN", 2023, 2024), _stint("NYG", 2025, 2025), _stint("DEN", 2025, None)],
                wiki_draft={"undrafted_year": 2019}),
        _player("8", "Pat Surtain II", "2", den(2021), {"year": 2021, "round": 1, "pick": 9, "team": "DEN"}),
        _player("9", "Jahdae Barron", "23", den(2025), {"year": 2025, "round": 1, "pick": 20, "team": "DEN"}),
        _player("10", "Ja'Quan McMillian", "29", den(2022), wiki_draft={"undrafted_year": 2022}),
        _player("11", "Dondrea Tillman", "92", [_stint("Birmingham Stallions", 2022, 2024, "UFL"), _stint("DEN", 2024, None)],
                wiki_draft={"undrafted_year": 2022}),
        _player("12", "Jeremy Crawshaw", "16", den(2025), {"year": 2025, "round": 6, "pick": 216, "team": "DEN"}),
        _player("13", "Devon Key", "26", [_stint("ATL", 2022, 2022), _stint("DEN", 2022, 2022), _stint("DEN", 2023, None)],
                wiki_draft={"undrafted_year": 2021}),
    ]
    coaches = [
        {"id": "coach-sean-payton", "name": "Sean Payton", "title": "HC", "side": "HC"},
        {"id": "coach-davis-webb", "name": "Davis Webb", "title": "OC", "side": "OFF"},
        {"id": "coach-robert-livingston", "name": "Robert Livingston", "title": "DPGC", "side": "DEF"},
    ]
    careers = {
        "coach-sean-payton": [_stint("NO", 2006, 2011), _stint("Liberty Christian (TX)", 2012, 2012, ""),
                              _stint("NO", 2013, 2021), _stint("DEN", 2023, None)],
        "coach-davis-webb": [_stint("DEN", 2023, None)],
        "coach-robert-livingston": [_stint("Colorado", 2024, 2025, ""), _stint("DEN", 2026, None)],
    }
    pmap = {p["id"]: p for p in people}
    for c in coaches:
        pmap[c["id"]] = {**c, "kind": "coach", "stints": careers[c["id"]]}
    chart = [
        {"slot": "LCB", "ids": ["8", "9"]}, {"slot": "NB", "ids": ["10", "9"]},
        {"slot": "WLB", "ids": ["11"]}, {"slot": "FS", "ids": ["13"]},
        {"slot": "P", "ids": ["12"]}, {"slot": "H", "ids": ["12"]}, {"slot": "PR", "ids": ["5", "6"]},
        *stripe_rows("WR", ["3", "4", "5", "6", "7"]),
        {"slot": "QB", "ids": ["1", "2"]},
    ]
    return {"version": 1, "fetched_at": "2026-09-20T12:00:00", "season": 2026,
            "chart": chart, "coaches": coaches, "people": pmap}


_OVERRIDES = {"trades": {"Jaylen Waddle": ["MIA"], "Jarrett Stidham": ["NE"], "Sean Payton": ["NO:2021"]},
              "salaries": {"Pat Bryant": 1139140}}


@pytest.fixture
def cardset():
    return AcBroncosCardSet(snapshot=_snapshot(), overrides=_OVERRIDES)


def _card(cardset, name, variant):
    return next(c for c in cardset.cards if c._person.name == name and c.variant == variant)


# ── wikitext parsing ─────────────────────────────────────────────────────────

def test_stints_year_templates_and_present():
    field = """
* [[Miami Dolphins]] ({{NFL Year|2021}}–{{NFL Year|2025}})
* [[New Orleans Saints]] ({{NFL Year|2019|2021}})*
* Denver Broncos ({{NFL Year|2025|present}})
"""
    assert [(s["team"], s["start"], s["end"]) for s in parse_stints(field)] == [
        ("NO", 2019, 2021), ("MIA", 2021, 2025), ("DEN", 2025, None)]


def test_stints_non_nfl_club_keeps_name_and_last_league():
    s = parse_stints("* [[Birmingham Stallions (2022)|Birmingham Stallions]] ({{USFL Year|2022}}–{{UFL Year|2024}})")[0]
    assert (s["team"], s["league"], s["end"]) == ("Birmingham Stallions", "UFL", 2024)


def test_stints_split_ranges_skip_subbullets_and_roles():
    field = """
* [[New Orleans Saints]] ({{nfly|2006|2011}}, {{nfly|2013|2021}})<br> Head coach
* [[Liberty Christian School (Argyle, Texas)|Liberty Christian (TX)]] (2012){{efn-ua|While suspended (2012) he coached
** Offensive coordinator ({{nfly|2000|2002}})
* [[History of the Oakland Raiders|Oakland]] / [[Las Vegas Raiders]] ({{nfly|2019}}–{{nfly|2021}})<br>Senior assistant
"""
    assert [(s["team"], s["start"], s["end"]) for s in parse_stints(field)] == [
        ("NO", 2006, 2011), ("Liberty Christian (TX)", 2012, 2012), ("NO", 2013, 2021), ("LV", 2019, 2021)]


def test_infobox_field_when_infobox_closes_on_last_bullet():
    text = "{{Infobox NFL biography\n|name=X\n|pastcoaching=\n* [[Auburn Tigers football|Auburn]] (2021–2022)\n* [[Denver Broncos]] ({{NFL Year|2025}}–present)<br>Coach}}\n\n'''X''' is a coach."
    assert [s["team"] for s in parse_stints(infobox_field(text, ["pastcoaching"]))] == ["Auburn", "DEN"]


def test_wiki_draft_drafted_and_undrafted():
    assert parse_wiki_draft("| draftyear = 2021\n| draftround = 1\n| draftpick = 6\n}}") == {"year": 2021, "round": 1, "pick": 6}
    assert parse_wiki_draft("| undraftedyear = 2019\n| pastteams =\n}}") == {"undrafted_year": 2019}


def test_staff_template_keeps_only_mapped_titles():
    text = ";Head coach\n*Head coach – [[Sean Payton]]\n*Assistant to the head coach – Paul Kelly\n;Defensive coaches\n*Front seven - [[Michael Wilhoite]]\n*Defensive pass game coordinator – [[Robert Livingston (American football)|Robert Livingston]]\n"
    staff = parse_staff(text, {"head coach": "HC", "defensive pass game coordinator": "DPGC"})
    assert [(c["name"], c["title"], c["side"]) for c in staff] == [
        ("Sean Payton", "HC", "HC"), ("Robert Livingston", "DPGC", "DEF")]
    assert staff[1]["wiki"] == "Robert Livingston (American football)"


def test_wr_list_is_striped_into_three_rows():
    rows = stripe_rows("WR", list("abcdef"))
    assert [r["ids"] for r in rows] == [["a", "d"], ["b", "e"], ["c", "f"]]
    assert stripe_rows("QB", list("ab")) == [{"slot": "QB", "ids": ["a", "b"]}]


# ── refresh policy ───────────────────────────────────────────────────────────

def test_stale_once_a_tuesday_has_passed():
    sunday = datetime(2026, 9, 20, 9, 0)                       # fetched Sunday
    snap = {"version": 1, "fetched_at": sunday.isoformat()}
    assert most_recent_tuesday(sunday) == datetime(2026, 9, 15)
    assert not is_stale(snap, datetime(2026, 9, 21, 23, 0))    # Monday: still fresh
    assert is_stale(snap, datetime(2026, 9, 22, 0, 5))         # Tuesday: refetch
    assert is_stale(None) and is_stale({"version": 0, "fetched_at": sunday.isoformat()})


# ── shared helpers ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("answer,name,ok", [
    ("riley moss", "Riley Moss", True),
    ("moss", "Riley Moss", True),                   # surname alone is enough
    ("riley", "Riley Moss", False),                 # first name alone is not
    ("surtain", "Pat Surtain II", True),
    ("abrams draine", "Kris Abrams-Draine", True),
    ("humphry", "Lil'Jordan Humphrey", True),
    ("hum", "Lil'Jordan Humphrey", False),
    ("riley ross", "Riley Moss", True),            # budget is per answer, not per word
    ("rily moss", "Riley Moss", True),
    ("even engram", "Evan Engram", True),          # one vowel off
    ("evan engrma", "Evan Engram", True),          # adjacent swap is one slip
    ("ivan engram", "Evan Engram", True),
    ("evan ingrum", "Evan Engram", True),           # two slips in a long name
    ("ivan ingrum", "Evan Engram", False),          # three is too many
    ("courtlend suton", "Courtland Sutton", True), # a slip in each word
    ("talanoa hufunga", "Talanoa Hufanga", True),
    ("pat bryan", "Pat Bryant", True),
    ("jk dobbins", "J.K. Dobbins", True),
    ("jaquan mcmillan", "Ja'Quan McMillian", True),
    ("marvin mims", "Marvin Mims Jr.", True),
    ("pat surtain ii", "Pat Surtain II", True),
    ("kris abramsdraine", "Kris Abrams-Draine", True),
    ("kris abrams-draine", "Kris Abrams-Draine", True),
    ("bo nik", "Bo Nix", True),                     # short name: one slip
    ("bo nck", "Bo Nix", False),
    ("ri* mo*", "Riley Moss", False),
    ("", "Riley Moss", False),
])
def test_person_name_match(answer, name, ok):
    assert person_name_match(answer, name) is ok


def test_ordering_helpers():
    assert chunk_evenly(list(range(7)), 6) == [[0, 1, 2, 3], [4, 5, 6]]
    assert chunk_evenly([], 6) == []
    assert batched_variant_order([["a", "b"], ["c"]], ["x", "y"], valid_ids={"a-x", "b-x", "a-y", "c-y"}) == \
        ["a-x", "b-x", "a-y", "c-y"]


def test_justify_is_color_aware():
    line = justify("\033[91mleft\033[0m", "right", 80)
    assert vis_len(line) == 80 and line.endswith("right")


# ── roster semantics ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,expected", [
    ("Bo Nix", "$2.5m (2024 1.12)"),
    ("Jaylen Waddle", "$17.2m (2026 MIA*)"),          # traded for
    ("Jarrett Stidham", "$6.5m (2023 LV)"),           # trade was earlier in his career, not to DEN
    ("Lil'Jordan Humphrey", "(2025 NYG)"),            # current stint, not his first
    ("Ja'Quan McMillian", "(2022 UDFA)"),
    ("Dondrea Tillman", "(2024 UFL)"),
    ("Devon Key", "(2022 ATL)"),                      # back-to-back DEN stints are one
    ("Pat Bryant", "$1.1m (2025 3.74)"),              # salary from overrides
    ("Sean Payton", "(2023 NO*)"),
    ("Davis Webb", "(2023)"),
    ("Robert Livingston", "(2026 Colorado)"),
])
def test_annotation(cardset, name, expected):
    person = next(p for p in cardset.roster.people.values() if p.name == name)
    assert cardset.roster.annotation(person) == expected


def test_slots_exclude_duties_and_stripe_wrs(cardset):
    slots = {p.name: p.slots for p in cardset.roster.players()}
    assert slots["Jahdae Barron"] == ["LCB2", "NB2"]
    assert slots["Jeremy Crawshaw"] == ["P1"]
    assert slots["Marvin Mims Jr."] == ["WR1"]
    assert slots["Pat Bryant"] == ["WR2"] and slots["Lil'Jordan Humphrey"] == ["WR2"]


def test_history_lines(cardset):
    waddle = next(p for p in cardset.roster.people.values() if p.name == "Jaylen Waddle")
    assert _plain(cardset.roster.history(waddle)).split("\n") == [
        "Jaylen Waddle, Wide Receiver", "  2021-25    MIA* (drafted 1.6)", "  2026-      DEN"]
    header = lambda name: _plain(cardset.roster.history(
        next(p for p in cardset.roster.people.values() if p.name == name))).split("\n")[0]
    assert header("Jahdae Barron") == "Jahdae Barron, Left Cornerback, 2nd string / Nickelback, 2nd string"
    assert header("Jeremy Crawshaw") == "Jeremy Crawshaw, Punter"          # holder duty isn't his position
    assert header("Sean Payton") == "Sean Payton"                          # no title map in these overrides
    titled = AcBroncosCardSet(snapshot=_snapshot(), overrides={"coach_titles": {
        "Offensive coordinator/assistant head coach": "OC", "Offensive coordinator": "OC",
        "Defensive pass game coordinator": "DPGC", "Quarterbacks": "QB"}}).roster
    assert _plain(titled.history(titled.people["coach-davis-webb"])).startswith("Davis Webb, Offensive Coordinator\n")
    # An entry year that matches no first stint keeps its own line.
    key = next(p for p in cardset.roster.people.values() if p.name == "Devon Key")
    assert _plain(cardset.roster.history(key)).split("\n")[1:3] == ["  2021       undrafted", "  2022       ATL"]
    tillman = next(p for p in cardset.roster.people.values() if p.name == "Dondrea Tillman")
    assert "  2022-24    Birmingham Stallions (undrafted)" in _plain(cardset.roster.history(tillman))
    payton = cardset.roster.people["coach-sean-payton"]
    text = _plain(cardset.roster.history(payton))
    assert "drafted" not in text and "  2013-21    NO*" in text and "  2006-11    NO\n" in text


# ── rendering ────────────────────────────────────────────────────────────────

def test_unit_table_bolds_player_and_his_rows_dims_unavailable(cardset):
    table = cardset.roster.unit_table(_card(cardset, "Pat Bryant", "pos")._person)
    lines = table.split("\n")
    assert [_plain(l).split()[0] for l in lines] == ["QB", "WR", "WR", "WR"]   # one skill-positions table
    assert "\033[1mWR\033[0m" in lines[1] and "\033[1m13 Pat Bryant\033[0m" in lines[1]
    assert "\033[1m" not in lines[0] and "\033[1m" not in lines[2]
    assert "\033[2m19 Marvin Mims Jr.\033[0m" in lines[3]
    assert _plain(lines[2]).endswith("14 Courtland Sutton   5 Lil'Jordan Humphrey")   # one-digit numbers pad


def test_table_shortens_other_names_to_fit_80():
    names = ["Evan Engram", "Adam Trautman", "Nate Adkins", "Dallen Bentley", "Caleb Lohner", "Lucas Krull"]
    rows = [("TE", True, [_Cell(n, bold=(n == "Nate Adkins")) for n in names])]
    line = _plain(render_table(rows, 80))
    assert len(line) <= 80
    assert "Nate Adkins" in line and "E. Engram" in line and "Evan Engram" not in line


def test_table_ellipsizes_when_short_names_still_overflow():
    rows = [("X", False, [_Cell(f"Firstname Extraordinarilylongsurname{i}") for i in range(5)])]
    line = _plain(render_table(rows, 80))
    assert len(line) <= 80 and "…" in line


def test_short_name():
    assert short_name("Marvin Mims Jr.") == "M. Mims Jr." and short_name("Cher") == "Cher"


def test_staff_table_shows_titles(cardset):
    table = _plain(cardset.roster.unit_table(cardset.roster.people["coach-davis-webb"]))
    assert "OC Davis Webb" in table and "DPGC Robert Livingston" in table
    assert table.split("\n")[0].startswith("HC")


# ── cards ────────────────────────────────────────────────────────────────────

def test_main_line_is_80_wide_with_one_blank(cardset):
    for card in cardset.cards:
        line = _plain(card.clue_text())
        assert len(line) <= 80 and line.count("??") == 1
    assert _plain(_card(cardset, "Marvin Mims Jr.", "num").clue_text()).startswith("#?? Marvin Mims Jr., WR (O)")
    assert _plain(_card(cardset, "Bo Nix", "name").clue_text()).startswith("#10 ??, QB ")
    assert _plain(_card(cardset, "Sean Payton", "title").clue_text()).startswith("Sean Payton, ??")


def test_position_needs_exact_slot_and_depth(cardset):
    barron = _card(cardset, "Jahdae Barron", "pos")
    assert barron.isCorrect("lcb2") and barron.isCorrect("NB2")
    assert not barron.isCorrect("LCB") and not barron.isCorrect("NB")     # both are 2s
    assert not barron.isCorrect("CB2") and not barron.isCorrect("LCB1")


def test_starters_may_drop_the_1_backups_need_their_digit(cardset):
    nix = _card(cardset, "Bo Nix", "pos")
    assert nix.isCorrect("qb") and nix.isCorrect("QB1") and not nix.isCorrect("qb2")
    assert nix.answer_key == "QB1"                              # the alias is not his identity
    assert not _card(cardset, "Jarrett Stidham", "pos").isCorrect("qb")
    assert _card(cardset, "Marvin Mims Jr.", "pos").isCorrect("wr")      # all three WR1s
    assert not _card(cardset, "Pat Bryant", "pos").isCorrect("wr")       # WR2
    assert not _card(cardset, "Jeremy Crawshaw", "pos").isCorrect("h")   # duty rows never count


def test_number_answers(cardset):
    nix = _card(cardset, "Bo Nix", "num")
    assert nix.isCorrect("10") and nix.isCorrect("#10") and not nix.isCorrect("1")
    assert not nix.getAnswer().isValid("ten") and nix.getAnswer().isValid("12")


def test_coach_cards(cardset):
    assert {c.variant for c in cardset.cards if c._person.kind == "coach"} == {"title", "name"}
    assert _card(cardset, "Robert Livingston", "title").isCorrect("dpgc")
    assert _card(cardset, "Robert Livingston", "name").isCorrect("livingston")
    assert not _card(cardset, "Robert Livingston", "name").isCorrect("robert")


def test_reveal_colors_the_answer(cardset):
    card = _card(cardset, "Bo Nix", "name")
    assert "\033[92mBo Nix\033[0m" in card.clue_text("bo nix", revealed=True)
    assert "\033[91mBo Nix\033[0m" in card.clue_text("", revealed=True)


def test_nothing_shown_before_answering(cardset):
    assert all(c.live_context() == "" for c in cardset.cards)


# ── order ────────────────────────────────────────────────────────────────────

def test_new_card_order_starters_lead_coaches_backups_then_assistants(cardset):
    order = cardset.new_card_order
    assert sorted(order) == sorted(c.id for c in cardset.cards)
    # first batch is the skill-position starters: all four slots before any number
    assert order[:12] == ["1-pos", "3-pos", "4-pos", "5-pos", "1-num", "3-num", "4-num", "5-num",
                          "1-name", "3-name", "4-name", "5-name"]
    pos = {cid: i for i, cid in enumerate(order)}
    last_starter = max(pos[f"{i}-name"] for i in ("1", "3", "8", "10", "11", "12", "13"))
    backups = [pos[f"{i}-{v}"] for i in ("2", "6", "7", "9") for v in ("pos", "name")]
    leads = [pos[f"coach-{c}-{v}"] for c in ("sean-payton", "davis-webb") for v in ("title", "name")]
    assistant = [pos[f"coach-robert-livingston-{v}"] for v in ("title", "name")]
    assert last_starter < min(leads) and max(leads) < min(backups) and max(backups) < min(assistant)
    assert pos["coach-sean-payton-title"] < pos["coach-davis-webb-title"] < pos["coach-sean-payton-name"]


def test_display_text_is_history_then_titled_table(cardset):
    from datetime import datetime
    roster = cardset.roster
    bryant = _card(cardset, "Pat Bryant", "pos")
    now = datetime(2026, 9, 26, 9, 0)
    assert _plain(roster.table_title(bryant._person, now)) == "Skill positions depth chart (ESPN, 6 days ago)"
    assert _plain(roster.table_title(bryant._person, datetime(2026, 9, 21, 1, 0))).endswith("(ESPN, 1 day ago)")
    assert _plain(roster.table_title(roster.people["coach-davis-webb"], datetime(2026, 9, 20, 23, 0))) \
        == "Coaching staff (Wikipedia, today)"
    lines = _plain(bryant.getAnswer().getDisplayText()).split("\n")
    title = next(i for i, l in enumerate(lines) if l.startswith("Skill positions depth chart"))
    assert lines[0] == "Pat Bryant, Wide Receiver, 2nd string" and lines[title - 1] == "" and lines[title + 1].startswith("  QB")


# ── scheduler: forget a card whose answer changed ────────────────────────────

def test_changed_answer_resets_only_that_card(tmp_path):
    store = AcReviewStore(str(tmp_path))
    before = AcBroncosCardSet(snapshot=_snapshot(), overrides=_OVERRIDES)
    sched = AcScheduler(before, store)
    for variant in ("pos", "num", "name"):
        sched.recordResult(_card(before, "Pat Bryant", variant), Rating.Good, 2.0)

    snap = _snapshot()
    snap["people"]["6"]["jersey"] = "81"          # new number …
    snap["people"]["6"]["salary"] = 5_000_000     # … and a raise, which is only a cue
    after = AcBroncosCardSet(snapshot=snap, overrides=_OVERRIDES)
    AcScheduler(after, store)

    state = store.load("broncos")
    assert "6-num" not in state["cards"]
    assert "6-pos" in state["cards"] and "6-name" in state["cards"]
    assert len(state["archived"]["6-num"][0]["reviews"]) == 1


def test_unchanged_answers_keep_their_state(tmp_path):
    store = AcReviewStore(str(tmp_path))
    cs = AcBroncosCardSet(snapshot=_snapshot(), overrides=_OVERRIDES)
    AcScheduler(cs, store).recordResult(_card(cs, "Bo Nix", "pos"), Rating.Good, 2.0)
    AcScheduler(AcBroncosCardSet(snapshot=_snapshot(), overrides=_OVERRIDES), store)
    state = store.load("broncos")
    assert "1-pos" in state["cards"] and "archived" not in state


# ── the committed seed ───────────────────────────────────────────────────────

def test_seed_snapshot_builds_a_full_deck():
    cs = AcBroncosCardSet(refresh=False)
    assert len(cs.roster.coaches) == 16
    assert len(cs.roster.players()) >= 53
    assert sorted(cs.new_card_order) == sorted(c.id for c in cs.cards)
    for card in cs.cards:
        assert len(_plain(card.clue_text())) <= 80
        for line in _plain(card.getAnswer().getDisplayText()).split("\n"):
            assert len(line) <= 80
    unsourced = [p.name for p in cs.roster.people.values() if not cs.roster.acquired(p)]
    assert unsourced == []
