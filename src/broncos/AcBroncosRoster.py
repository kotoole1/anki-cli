"""The roster as the broncos cards see it: people, their slots, and the text
shown around a card (main-line annotation, career history, titled unit table).

Responsibility: everything derivable from a snapshot + overrides with no I/O
and no notion of cards or scheduling. AcBroncosData decides what the facts
are; this module decides what they mean and how they read:

  * which depth-chart rows make up a unit table, and a player's quizzed slot
    labels (row + depth, duties like PR/KR/H excluded);
  * "how he got here" — the year of the current Denver stint and where from,
    with an asterisk when the previous club traded him away;
  * the 80-column rendering of unit tables and histories, and the table's
    title line naming its source and how old the snapshot is.

Holds no state beyond the snapshot it was built from.
"""

from dataclasses import dataclass, field
from datetime import datetime

from cards.lineLayout import LINE_WIDTH, ellipsize, pad_to
from broncos.AcBroncosData import DUTY_SLOTS, UNITS

_TEAM = "DEN"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"

_COORDINATORS = ("HC", "OC", "DC", "STC")
_SIDE_ORDER = ("HC", "OFF", "DEF", "ST")
_STAFF_PER_LINE = 4
_COL_GAP = 2
_INDENT = "  "   # body lines under a bold heading (history, table)
_SPAN_W = 11   # "1999-2002" plus a gap
_CHART_SOURCE = "ESPN"
_STAFF_SOURCE = "Wikipedia"


@dataclass
class AcPerson:
    id: str
    kind: str                      # "player" | "coach"
    name: str
    jersey: str = ""
    status: str = ""               # "", "O", "IR", "off", … — shown, never quizzed
    salary: int | None = None
    draft: dict = field(default_factory=dict)       # {year, round, pick, team}
    undrafted_year: int | None = None
    stints: list[dict] = field(default_factory=list)
    traded_from: set = field(default_factory=set)   # indices into stints
    positions: list[tuple[str, int]] = field(default_factory=list)  # players: [("LCB", 2), ("NB", 2)]
    title: str = ""                # coaches: "OC"
    full_title: str = ""           # coaches: "Offensive Coordinator"
    side: str = ""                 # coaches: HC / OFF / DEF / ST

    @property
    def available(self) -> bool:
        return self.status == ""

    @property
    def slots(self) -> list[str]:
        """["LCB2", "NB2"] — the full labels; the pos card's identity (answer_key)."""
        return [f"{slot}{depth}" for slot, depth in self.positions]

    @property
    def slot_aliases(self) -> list[str]:
        """Depth-less spellings also accepted: a starter's "1" may be left off
        (QB = QB1), a backup's digit may not."""
        return [slot for slot, depth in self.positions if depth == 1]

    @property
    def shown_slots(self) -> list[str]:
        """`slots` as displayed: a starter reads "QB", never "QB1"."""
        return [slot if depth == 1 else f"{slot}{depth}" for slot, depth in self.positions]

    @property
    def spelled_out(self) -> str:
        """"Left Cornerback, 2nd string / Nickelback, 2nd string"; a starter is
        just "Quarterback". Coaches read their full title."""
        if self.kind == "coach":
            return self.full_title
        return " / ".join(_SLOT_NAMES.get(slot, slot) + (f", {_ordinal(depth)} string" if depth > 1 else "")
                          for slot, depth in self.positions)


_SLOT_NAMES = {
    "QB": "Quarterback", "RB": "Running Back", "FB": "Fullback", "WR": "Wide Receiver", "TE": "Tight End",
    "LT": "Left Tackle", "LG": "Left Guard", "C": "Center", "RG": "Right Guard", "RT": "Right Tackle",
    "LDE": "Left Defensive End", "NT": "Nose Tackle", "RDE": "Right Defensive End",
    "WLB": "Weakside Linebacker", "LILB": "Left Inside Linebacker",
    "RILB": "Right Inside Linebacker", "SLB": "Strongside Linebacker",
    "LCB": "Left Cornerback", "SS": "Strong Safety", "FS": "Free Safety",
    "RCB": "Right Cornerback", "NB": "Nickelback",
    "PK": "Kicker", "P": "Punter", "H": "Holder", "PR": "Punt Returner", "KR": "Kick Returner",
    "LS": "Long Snapper",
}


def _ordinal(n: int) -> str:
    if n % 100 in (11, 12, 13):
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def _full_titles(coach_titles: dict[str, str]) -> dict[str, str]:
    """overrides' full title → abbreviation map, inverted. Several full titles
    share an abbreviation ("… coordinator/assistant head coach"); the shortest
    is the one that's true of whoever holds it. Position groups gain "Coach"."""
    out: dict[str, str] = {}
    for full, abbr in coach_titles.items():
        if abbr not in out or len(full) < len(out[abbr]):
            out[abbr] = full
    return {abbr: (full if "coach" in full.lower() or "coordinator" in full.lower() else f"{full} coach").title()
            for abbr, full in out.items()}


def short_name(name: str) -> str:
    first, _, rest = name.partition(" ")
    return f"{first[0]}. {rest}" if rest else name


def _span(start: int, end: int | None) -> str:
    if end is None:
        return f"{start}-"
    if end == start:
        return str(start)
    return f"{start}-{end % 100:02d}" if end // 100 == start // 100 else f"{start}-{end}"


def _age(today, fetched) -> str:
    days = max(0, (today - fetched).days)
    return "today" if days == 0 else "1 day ago" if days == 1 else f"{days} days ago"


def _traded_indices(stints: list[dict], marks: list[str]) -> set:
    """overrides' "TEAM" / "TEAM:endyear" marks → indices of the stints that
    ended in a trade. The final stint can't have been traded away from."""
    out = set()
    for mark in marks:
        team, _, year = mark.partition(":")
        for i, s in enumerate(stints[:-1]):
            if s["team"] == team and (not year or s["end"] == int(year)):
                out.add(i)
    return out


class AcBroncosRoster:
    def __init__(self, snapshot: dict, overrides: dict):
        self.rows = self._order_rows(snapshot["chart"])       # [(unit, slot, [ids])]
        self.fetched_at = snapshot.get("fetched_at")          # ISO string, for table titles
        self.people: dict[str, AcPerson] = {}
        for raw in snapshot["people"].values():
            self.people[raw["id"]] = self._person(raw, overrides)
        self.coaches = [self.people[c["id"]] for c in snapshot.get("coaches", [])
                        if c["id"] in self.people]
        self._assign_slots()

    # ── construction ─────────────────────────────────────────────────────────

    @staticmethod
    def _order_rows(chart: list[dict]) -> list[tuple[str, str, list[str]]]:
        unit_of = {slot: (u, i) for u, (_, slots) in enumerate(UNITS) for i, slot in enumerate(slots)}
        keyed = []
        for n, row in enumerate(chart):
            u, i = unit_of.get(row["slot"], (len(UNITS), 0))
            keyed.append(((u, i, n), row))
        names = [name for name, _ in UNITS] + ["Other"]
        return [(names[k[0]], row["slot"], list(row["ids"])) for k, row in sorted(keyed, key=lambda kr: kr[0])]

    @staticmethod
    def _person(raw: dict, overrides: dict) -> AcPerson:
        name = raw["name"]
        stints = overrides.get("stints", {}).get(name) or raw.get("stints") or []
        draft = raw.get("draft") or {}
        wiki_draft = raw.get("wiki_draft") or {}
        if not draft and wiki_draft.get("round"):
            draft = wiki_draft
        return AcPerson(
            id=raw["id"], kind=raw["kind"], name=name,
            jersey=str(raw.get("jersey") or ""), status=raw.get("status") or "",
            salary=raw.get("salary") or overrides.get("salaries", {}).get(name),
            draft=draft, undrafted_year=wiki_draft.get("undrafted_year"),
            stints=stints,
            traded_from=_traded_indices(stints, overrides.get("trades", {}).get(name, [])),
            title=raw.get("title", ""), side=raw.get("side", ""),
            full_title=_full_titles(overrides.get("coach_titles", {})).get(raw.get("title", ""), ""),
        )

    def _assign_slots(self) -> None:
        duties: dict[str, list[tuple[str, int]]] = {}
        for _, slot, ids in self.rows:
            for depth, pid in enumerate(ids, start=1):
                if slot in DUTY_SLOTS:
                    duties.setdefault(pid, []).append((slot, depth))
                else:
                    self.people[pid].positions.append((slot, depth))
        for pid, held in duties.items():     # a pure returner still needs a slot
            if not self.people[pid].positions:
                self.people[pid].positions = held

    # ── learning order ───────────────────────────────────────────────────────

    def players(self) -> list[AcPerson]:
        return [p for p in self.people.values() if p.kind == "player" and p.slots]

    def unit_depth_order(self) -> list[tuple[str, int, list[str]]]:
        """(unit, depth, [player ids]) — each unit's starters, then its 2s, …
        A player is listed once, at his first appearance; duty rows are skipped."""
        seen, out = set(), []
        units = list(dict.fromkeys(u for u, _, _ in self.rows))
        for unit in units:
            rows = [ids for u, slot, ids in self.rows if u == unit and slot not in DUTY_SLOTS]
            for depth in range(max((len(r) for r in rows), default=0)):
                ids = [r[depth] for r in rows if depth < len(r) and r[depth] not in seen]
                ids = list(dict.fromkeys(ids))
                seen.update(ids)
                if ids:
                    out.append((unit, depth + 1, ids))
        return out

    def lead_coaches(self) -> list[str]:
        """Head coach and coordinators."""
        return [c.id for c in self.coaches if c.title in _COORDINATORS]

    def assistant_groups(self) -> list[list[str]]:
        """Position and assistant coaches: the offensive staff, then defensive, …"""
        rest = [[c.id for c in self.coaches if c.side == side and c.title not in _COORDINATORS]
                for side in _SIDE_ORDER]
        return [g for g in rest if g]

    # ── main-line annotation ─────────────────────────────────────────────────

    def acquired(self, p: AcPerson) -> str:
        """"(2023 3.83)" / "(2025 SF)" / "(2026 MIA*)" / "(2022 UDFA)" — when the
        current Denver stint began and where he came from. Back-to-back DEN
        stints (a cut and practice-squad re-sign) count as one."""
        den = [i for i, s in enumerate(p.stints) if s["team"] == _TEAM]
        if not den:
            if p.draft.get("team") == _TEAM:
                return f"({p.draft['year']} {p.draft['round']}.{p.draft['pick']})"
            return ""
        i = den[-1]
        while i > 0 and p.stints[i - 1]["team"] == _TEAM:
            i -= 1
        year = p.stints[i]["start"]
        if i == 0:
            if p.kind == "coach":
                return f"({year})"
            if p.draft.get("round") and p.draft.get("team") in (_TEAM, None):
                return f"({year} {p.draft['round']}.{p.draft['pick']})"
            if p.draft.get("round"):
                return f"({year} {p.draft['team']})"
            return f"({year} UDFA)"
        prev = p.stints[i - 1]
        nfl = prev.get("league") == "NFL"
        source = prev["team"] if nfl or not prev.get("league") else prev["league"]
        return f"({year} {source}{'*' if i - 1 in p.traded_from else ''})"

    def annotation(self, p: AcPerson) -> str:
        parts = []
        if p.salary:
            parts.append(f"${p.salary / 1e6:.1f}m")
        if self.acquired(p):
            parts.append(self.acquired(p))
        return " ".join(parts)

    # ── post-answer text ─────────────────────────────────────────────────────

    def history(self, p: AcPerson) -> str:
        lines = [f"{_BOLD}{p.name}{_RESET}" + (f", {p.spelled_out}" if p.spelled_out else "")]
        # How he entered the league rides on the first stint's line; it only
        # gets a line (and a year) of its own when there's no stint to match.
        entry, entry_year = "", None
        if p.kind == "player":
            if p.draft.get("round"):
                entry, entry_year = f"drafted {p.draft['round']}.{p.draft['pick']}", p.draft["year"]
            elif p.undrafted_year:
                entry, entry_year = "undrafted", p.undrafted_year
        if entry and (not p.stints or p.stints[0]["start"] != entry_year):
            lines.append(f"{_INDENT}{entry_year:<{_SPAN_W}}{entry}")
            entry = ""
        for i, s in enumerate(p.stints):
            star = "*" if i in p.traded_from else ""
            note = f" ({entry})" if entry and i == 0 else ""
            lines.append(f"{_INDENT}{_span(s['start'], s['end']):<{_SPAN_W}}{s['team']}{star}{note}")
        if len(lines) == 1:
            lines.append(f"{_INDENT}{_DIM}(no career history found){_RESET}")
        return "\n".join(lines)

    def _unit_of(self, p: AcPerson) -> str:
        mine = [(u, slot) for u, slot, ids in self.rows if p.id in ids]
        return next((u for u, slot in mine if slot not in DUTY_SLOTS), mine[0][0])

    def table_title(self, p: AcPerson, now: datetime | None = None) -> str:
        """"O-Line depth chart (ESPN, 6 days ago)" — what the table below it is,
        where it came from, and how old the snapshot is."""
        if p.kind == "coach":
            what, source = "Coaching staff", _STAFF_SOURCE
        else:
            what, source = f"{self._unit_of(p)} depth chart", _CHART_SOURCE
        notes = [source]
        if self.fetched_at:
            notes.append(_age((now or datetime.now()).date(), datetime.fromisoformat(self.fetched_at).date()))
        return f"{_BOLD}{what}{_RESET} {_DIM}({', '.join(notes)}){_RESET}"

    def titled_table(self, p: AcPerson, now: datetime | None = None) -> str:
        """The title, then the table indented under it the way a history's
        lines sit under the name."""
        table = self.unit_table(p, LINE_WIDTH - len(_INDENT))
        return "\n".join([self.table_title(p, now)] + [_INDENT + line for line in table.split("\n")])

    def unit_table(self, p: AcPerson, width: int = LINE_WIDTH) -> str:
        if p.kind == "coach":
            return self._staff_table(p, width)
        unit = self._unit_of(p)
        rows = []
        for u, slot, ids in self.rows:
            if u != unit:
                continue
            # Numbers are right-aligned to two digits so names line up too.
            cells = [_Cell(self.people[i].name, bold=i == p.id, dim=not self.people[i].available,
                           prefix=f"{self.people[i].jersey:>2} ")
                     for i in ids]
            rows.append((slot, p.id in ids, cells))
        return render_table(rows, width)

    def _staff_table(self, p: AcPerson, width: int) -> str:
        rows = []
        for side in _SIDE_ORDER:
            staff = [c for c in self.coaches if c.side == side]
            for n in range(0, len(staff), _STAFF_PER_LINE):
                cells = [_Cell(c.name, bold=c.id == p.id, prefix=f"{c.title} ")
                         for c in staff[n:n + _STAFF_PER_LINE]]
                rows.append((side if n == 0 else "", False, cells))
        return render_table(rows, width)


@dataclass
class _Cell:
    name: str
    bold: bool = False
    dim: bool = False
    prefix: str = ""     # a player's number or a coach's title; never shortened


def render_table(rows: list[tuple[str, bool, list[_Cell]]], width: int = LINE_WIDTH) -> str:
    """Aligned columns within `width`. When full names don't fit, every name but
    the highlighted one becomes "F. Last"; if that still overflows, the widest
    column (the deepest, on a tie) is ellipsized a character at a time, so as
    few names as possible are cut. The highlighted cell is never cut."""
    label_w = max((len(label) for label, _, _ in rows), default=0) + _COL_GAP
    n_cols = max((len(cells) for _, _, cells in rows), default=0)

    def texts(shorten: bool, caps: dict[int, int]) -> list[list[str]]:
        out = []
        for _, _, cells in rows:
            line = []
            for i, c in enumerate(cells):
                name = c.name if c.bold or not shorten else short_name(c.name)
                text = c.prefix + name
                line.append(text if c.bold or i not in caps else ellipsize(text, caps[i]))
            out.append(line)
        return out

    def widths(grid: list[list[str]]) -> list[int]:
        return [max((len(line[i]) for line in grid if i < len(line)), default=0)
                for i in range(n_cols)]

    def total(ws: list[int]) -> int:
        return label_w + sum(ws) + _COL_GAP * max(0, n_cols - 1)

    grid = texts(False, {})
    if total(widths(grid)) > width:
        grid = texts(True, {})
    ws, caps, stuck = widths(grid), {}, set()
    while total(ws) > width:
        open_cols = [i for i in range(n_cols) if i not in stuck and ws[i] > 4]
        if not open_cols:
            break
        col = max(open_cols, key=lambda i: (ws[i], i))
        caps[col] = ws[col] - 1
        grid = texts(True, caps)
        if widths(grid)[col] == ws[col]:     # held open by the highlighted cell
            stuck.add(col)
        ws = widths(grid)

    lines = []
    for (label, label_bold, cells), line in zip(rows, grid):
        out = pad_to(f"{_BOLD}{label}{_RESET}" if label_bold else label, label_w)
        for i, (cell, text) in enumerate(zip(cells, line)):
            style = _BOLD if cell.bold else _DIM if cell.dim else ""
            styled = f"{style}{text}{_RESET}" if style else text
            out += pad_to(styled, ws[i] + _COL_GAP) if i < len(line) - 1 else styled
        lines.append(out.rstrip())
    return "\n".join(lines)
