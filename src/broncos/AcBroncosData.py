"""Roster snapshot for the broncos set: fetch, parse, cache, and load.

Responsibility: turn three live sources into one JSON "snapshot" the card set
can be built from with no network, and keep that snapshot fresh.

  * ESPN JSON APIs — depth chart, jersey numbers, salaries, injury status and
    draft pick. (espn.com's HTML pages sit behind a bot wall; these hosts don't.)
  * Wikipedia infoboxes — each person's career stints, machine-parsed.
  * Wikipedia's Broncos staff template — the coaching staff.

State owned here:
  * cache/snapshot.json (gitignored) — the latest successful refresh.
  * seed_snapshot.json (committed) — fallback so a fresh checkout works offline.
  * overrides.json (committed, hand-edited, never written by this module) — the
    facts no source exposes in a parseable way: which moves were trades, salary
    fill-ins, Wikipedia titles for ambiguous names, stints for people with no
    article, and the coach title → abbreviation map that doubles as the cut
    line for which coaches get cards.

Refresh policy: depth charts settle on Tuesdays, so a snapshot older than the
most recent Tuesday (local time) is stale and load_snapshot() refetches. Any
failure keeps the old snapshot — a study tool must open offline. Per-person
data that never changes (draft pick) or changes only when a player moves
(stints) is carried over from the previous snapshot, so a weekly refresh is a
handful of requests rather than one per player.
"""

import json
import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

_DIR = os.path.dirname(os.path.abspath(__file__))
_CACHE_PATH = os.path.join(_DIR, "cache", "snapshot.json")
_SEED_PATH = os.path.join(_DIR, "seed_snapshot.json")
_OVERRIDES_PATH = os.path.join(_DIR, "overrides.json")

_SNAPSHOT_VERSION = 1
_TEAM = "DEN"
_ESPN_TEAM_ID = "7"
_ROSTER_URL = f"https://site.web.api.espn.com/apis/site/v2/sports/football/nfl/teams/{_ESPN_TEAM_ID}/roster"
_DEPTH_URL = ("https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/"
              "seasons/{season}/teams/" + _ESPN_TEAM_ID + "/depthcharts")
_ATHLETE_URL = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/athletes/{id}"
_WIKI_RAW_URL = "https://en.wikipedia.org/w/index.php?action=raw&title={title}"
_WIKI_SEARCH_URL = ("https://en.wikipedia.org/w/api.php?action=query&list=search"
                    "&format=json&srlimit=3&srsearch={q}")
_STAFF_TEMPLATE = "Template:Denver Broncos staff"

# ESPN refuses non-browser agents; Wikipedia asks for a descriptive one.
_ESPN_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
_WIKI_UA = "anki-cli/0.1 (personal flashcard tool)"

_ESPN_TEAM_ABBR = {
    1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN", 8: "DET",
    9: "GB", 10: "TEN", 11: "IND", 12: "KC", 13: "LV", 14: "LAR", 15: "MIA", 16: "MIN",
    17: "NE", 18: "NO", 19: "NYG", 20: "NYJ", 21: "PHI", 22: "ARI", 23: "PIT", 24: "LAC",
    25: "SF", 26: "SEA", 27: "TB", 28: "WSH", 29: "CAR", 30: "JAX", 33: "BAL", 34: "HOU",
}

# Wikipedia article names, including the names relocated franchises used while
# current players/coaches were there.
NFL_TEAM_ABBR = {
    "Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF", "Carolina Panthers": "CAR", "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE", "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN", "Detroit Lions": "DET", "Green Bay Packers": "GB",
    "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC", "Las Vegas Raiders": "LV", "Oakland Raiders": "OAK",
    "Los Angeles Raiders": "RAI", "Los Angeles Chargers": "LAC", "San Diego Chargers": "SD",
    "Los Angeles Rams": "LAR", "St. Louis Rams": "STL", "Miami Dolphins": "MIA",
    "Minnesota Vikings": "MIN", "New England Patriots": "NE", "New Orleans Saints": "NO",
    "New York Giants": "NYG", "New York Jets": "NYJ", "Philadelphia Eagles": "PHI",
    "Pittsburgh Steelers": "PIT", "San Francisco 49ers": "SF", "Seattle Seahawks": "SEA",
    "Tampa Bay Buccaneers": "TB", "Tennessee Titans": "TEN", "Houston Oilers": "HOU",
    "Tennessee Oilers": "TEN", "Washington Commanders": "WSH",
    "Washington Football Team": "WSH", "Washington Redskins": "WSH",
}

# ESPN lists the wide receivers as one ranked list; its web page (the layout
# the user studies against) stripes that list across this many "WR" rows.
_WR_ROWS = 3

# Depth-chart rows → the unit table shown after an answer. Order here is the
# display order of units and of rows within a unit. Rows ESPN might add later
# (a 4-3 "MLB", say) land in a trailing "Other" unit rather than vanishing.
UNITS = [
    ("Skill positions", ["QB", "RB", "FB", "WR", "TE"]),
    ("O-Line", ["LT", "LG", "C", "RG", "RT"]),
    ("D-Line", ["LDE", "NT", "RDE"]),
    ("Linebackers", ["WLB", "LILB", "RILB", "SLB"]),
    ("D-backs", ["LCB", "SS", "FS", "RCB", "NB"]),
    ("Specialists", ["PK", "P", "H", "PR", "KR", "LS"]),
]
# Duties held by players who already have a real position; shown in the
# Specialists table but never part of a player's quizzed slot.
DUTY_SLOTS = frozenset({"H", "PR", "KR"})

_INJURY_TAGS = {"Out": "O", "Injured Reserve": "IR", "Doubtful": "D",
                "Physically Unable to Perform": "PUP", "Suspension": "SUSP"}


# ── http ──────────────────────────────────────────────────────────────────────

def _get(url: str, agent: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": agent})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8")


def _get_json(url: str) -> dict:
    return json.loads(_get(url.replace("http://", "https://"), _ESPN_UA))


def _wiki_raw(title: str) -> str | None:
    """Wikitext of `title`, following one redirect. None if the page is missing."""
    for _ in range(2):
        url = _WIKI_RAW_URL.format(title=urllib.parse.quote(title.replace(" ", "_")))
        try:
            text = _get(url, _WIKI_UA)
        except Exception:
            return None
        m = re.match(r"\s*#REDIRECT\s*\[\[([^\]|#]+)", text, re.I)
        if not m:
            return text
        title = m.group(1)
    return None


# ── wikitext parsing (pure; unit-tested) ─────────────────────────────────────

_YEAR_TEMPLATE_RE = re.compile(r"\{\{\s*([A-Za-z]+)[ _]?[Yy]ear\s*\|\s*(\d{4})\s*(?:\|\s*(\d{4}|present)\s*)?\}\}")
_NFLY_RE = re.compile(r"\{\{\s*nfly\s*\|\s*(\d{4})\s*(?:\|\s*(\d{4}|present)\s*)?\}\}", re.I)
_RANGE_RE = re.compile(r"(\d{4})(?:\s*[–—-]\s*(\d{4}|present))?", re.I)


def infobox_field(wikitext: str, names: list[str]) -> str:
    """Raw value of the first infobox parameter in `names` that is present."""
    for name in names:
        m = re.search(rf"^\s*\|\s*{name}\s*=(.*?)(?=^\s*\|\s*[\w ]+?\s*=|^\}}\}}|^\s*$)",
                      wikitext, re.S | re.M)
        if m and m.group(1).strip():
            return m.group(1)
    return ""


def _strip_markup(s: str) -> str:
    s = re.sub(r"<ref[^>]*?/>|<ref.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"\{\{\s*efn.*", "", s, flags=re.S | re.I)   # notes run to end of line
    return s


def parse_stints(field: str) -> list[dict]:
    """Career-history bullets → [{team, league, start, end}], oldest first.

    `team` is the NFL abbreviation when the club is an NFL franchise, else the
    name as Wikipedia displays it (colleges, CFL/UFL clubs). `end` is None for
    a stint that is still open. One bullet with two year ranges (a coach who
    left and came back) becomes two stints. Sub-bullets (role changes within a
    stint) are ignored. The sort is stable, so same-year moves keep the
    infobox's order."""
    stints = []
    for line in field.split("\n"):
        line = line.strip()
        if not line.startswith("*") or line.startswith("**"):
            continue
        line = _strip_markup(line[1:]).split("<br")[0]
        league = ""
        # A club that changed leagues mid-stint (USFL → UFL) is known by the last.
        templated = _YEAR_TEMPLATE_RE.findall(line)
        if templated:
            league = templated[-1][0].upper()
        elif _NFLY_RE.search(line):
            league = "NFL"
        line = _YEAR_TEMPLATE_RE.sub(lambda m: f"{m.group(2)}–{m.group(3)}" if m.group(3) else m.group(2), line)
        line = _NFLY_RE.sub(lambda m: f"{m.group(1)}–{m.group(2)}" if m.group(2) else m.group(1), line)

        # The club is everything before the year parenthesis. A relocated
        # franchise can be two links ("Oakland / Las Vegas Raiders"): the last
        # link that names an NFL club wins, else the first link's display text.
        # Link targets are masked first: "[[Birmingham Stallions (2022)|…]]"
        # carries a year in parentheses that isn't the stint's.
        masked = re.sub(r"\[\[.*?\]\]", lambda m: "_" * len(m.group(0)), line)
        cut = re.search(r"\((?=[^()]*\d{4})", masked)
        head, rest = (line[:cut.start()], line[cut.start():]) if cut else (line, "")
        links = [(t.strip(), (d or t).strip())
                 for t, d in re.findall(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", head)]
        if not links:
            links = [(head.strip(), head.strip())]
        team = links[0][1]
        for target, display in links:
            target = re.sub(r"\s*\(.*?\)$", "", target)
            team = NFL_TEAM_ABBR.get(target) or NFL_TEAM_ABBR.get(display) or team
        if team in NFL_TEAM_ABBR.values() and not league:
            league = "NFL"

        years = re.search(r"\(([^()]*\d{4}[^()]*)\)", rest)
        if not team or not years:
            continue
        for start, end in _RANGE_RE.findall(years.group(1)):
            stints.append({
                "team": team, "league": league, "start": int(start),
                "end": None if end.lower() == "present" else int(end or start),
            })
    return sorted(stints, key=lambda s: s["start"])


def parse_wiki_draft(wikitext: str) -> dict:
    """{'undrafted_year': int} or {'year','round','pick'} or {} from an infobox."""
    und = infobox_field(wikitext, ["undraftedyear"])
    if re.search(r"\d{4}", und):
        return {"undrafted_year": int(re.search(r"\d{4}", und).group())}
    out = {}
    for key, param in (("year", "draftyear"), ("round", "draftround"), ("pick", "draftpick")):
        m = re.search(r"\d+", infobox_field(wikitext, [param]))
        if m:
            out[key] = int(m.group())
    return out if len(out) == 3 else {}


def parse_staff(template_text: str, title_map: dict[str, str]) -> list[dict]:
    """Coaches from the staff template whose title is in `title_map`, in
    template order: [{name, title (abbreviation), side, wiki}]. `side` is the
    template section (HC / OFF / DEF / ST)."""
    sides = {"head coach": "HC", "offensive coaches": "OFF",
             "defensive coaches": "DEF", "special teams coaches": "ST"}
    coaches, side = [], None
    for line in template_text.split("\n"):
        line = line.strip()
        if line.startswith(";"):
            side = sides.get(line[1:].strip().lower())
            continue
        m = re.match(r"\*\s*(.+?)\s+[–—-]\s+(.+)$", line)
        if not (side and m):
            continue
        title, person = m.group(1).strip(), m.group(2).strip()
        abbr = title_map.get(title.lower())
        if not abbr:
            continue
        link = re.match(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", person)
        name = (link.group(2) or link.group(1)) if link else person
        name = re.sub(r"\s*\(.*?\)$", "", name).strip()
        coaches.append({"name": name, "title": abbr, "side": side,
                        "wiki": link.group(1) if link else None})
    return coaches


# ── wikipedia lookups ─────────────────────────────────────────────────────────

def _is_persons_page(text: str | None) -> bool:
    return bool(text) and "{{Infobox" in text and "Broncos" in text


def _find_wiki_page(name: str, title_hint: str | None) -> tuple[str | None, str | None]:
    """(title, wikitext) of the football person called `name`, or (None, None).
    Namesakes are common, so a candidate only counts if its article has an
    infobox and mentions the Broncos."""
    candidates = [title_hint] if title_hint else []
    candidates += [name, f"{name} (American football)"]
    for title in candidates:
        text = _wiki_raw(title)
        if _is_persons_page(text):
            return title, text
    try:
        q = urllib.parse.quote(f"{name} Denver Broncos")
        hits = json.loads(_get(_WIKI_SEARCH_URL.format(q=q), _WIKI_UA))["query"]["search"]
    except Exception:
        hits = []
    surname = name_key(name).split("-")[-1] if name else ""
    for hit in hits:
        if surname and surname not in name_key(hit["title"]):
            continue
        text = _wiki_raw(hit["title"])
        if _is_persons_page(text):
            return hit["title"], text
    return None, None


def _career_from_wiki(name: str, kind: str, overrides: dict) -> dict:
    title, text = _find_wiki_page(name, overrides.get("wiki_titles", {}).get(name))
    if not text:
        return {"wiki": None, "stints": [], "wiki_draft": {}}
    fields = (["pastcoaching", "coaching_teams", "coach_teams"] if kind == "coach"
              else ["pastteams", "teams"])
    return {"wiki": title,
            "stints": parse_stints(infobox_field(text, fields)),
            "wiki_draft": parse_wiki_draft(text) if kind == "player" else {}}


# ── ESPN ─────────────────────────────────────────────────────────────────────

def name_key(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _status_tag(athlete: dict, on_roster: bool) -> str:
    if not on_roster:
        return "off"
    for inj in athlete.get("injuries") or []:
        tag = _INJURY_TAGS.get(inj.get("status", ""))
        if tag:
            return tag
    return ""


def _espn_draft(athlete_detail: dict) -> dict:
    d = athlete_detail.get("draft") or {}
    if not d.get("round"):
        return {}
    m = re.search(r"/teams/(\d+)", (d.get("team") or {}).get("$ref", ""))
    return {"year": d.get("year"), "round": d["round"], "pick": d.get("selection"),
            "team": _ESPN_TEAM_ABBR.get(int(m.group(1))) if m else None}


def stripe_rows(slot: str, ids: list[str]) -> list[dict]:
    """One ranked list → the rows ESPN's page shows. Only WR is striped."""
    n = _WR_ROWS if slot == "WR" else 1
    return [{"slot": slot, "ids": ids[r::n]} for r in range(n) if ids[r::n]]


def _fetch_chart(season: int) -> list[dict]:
    """[{slot, ids}] in ESPN's row order, all formations flattened."""
    rows = []
    for formation in _get_json(_DEPTH_URL.format(season=season)).get("items", []):
        for pos in formation.get("positions", {}).values():
            entries = sorted(pos.get("athletes", []), key=lambda e: e.get("rank", 99))
            ids = [re.search(r"/athletes/(\d+)", e["athlete"]["$ref"]).group(1) for e in entries]
            rows += stripe_rows(pos["position"]["abbreviation"].upper(), ids)
    return rows


# ── refresh ───────────────────────────────────────────────────────────────────

def load_overrides() -> dict:
    with open(_OVERRIDES_PATH, encoding="utf-8") as f:
        return json.load(f)


def fetch_snapshot(previous: dict | None = None, progress=None) -> dict:
    """Build a fresh snapshot from the network. Raises on ESPN failure (the
    roster is the point); Wikipedia failures just leave a person's stints empty
    so the next refresh retries them."""
    say = progress or (lambda msg: None)
    overrides = load_overrides()
    prev_people = (previous or {}).get("people", {})

    say("roster")
    roster = _get_json(_ROSTER_URL)
    season = roster.get("season", {}).get("year") or datetime.now().year
    espn = {}
    for group in roster.get("athletes", []):
        if group.get("position") == "practiceSquad":
            continue
        for a in group.get("items", []):
            espn[a["id"]] = a

    say("depth chart")
    chart = _fetch_chart(season)
    chart_ids = list(dict.fromkeys(i for row in chart for i in row["ids"]))

    def build_player(pid: str) -> dict:
        old = prev_people.get(pid, {})
        a = espn.get(pid)
        detail = None
        if a is None or "draft" not in old:
            detail = _get_json(_ATHLETE_URL.format(id=pid))
        src = a or detail
        person = {
            "id": pid, "kind": "player",
            "name": src.get("displayName") or src.get("fullName"),
            "jersey": src.get("jersey") or "",
            "status": _status_tag(src, on_roster=a is not None),
            "salary": ((a or {}).get("contract") or {}).get("salary") or None,
            "draft": old["draft"] if "draft" in old else _espn_draft(detail),
        }
        return person

    say(f"{len(chart_ids)} players")
    with ThreadPoolExecutor(max_workers=8) as pool:
        people = {p["id"]: p for p in pool.map(build_player, chart_ids)}

    say("coaching staff")
    title_map = {k.lower(): v for k, v in overrides.get("coach_titles", {}).items()}
    try:
        staff = parse_staff(_wiki_raw(_STAFF_TEMPLATE) or "", title_map)
    except Exception:
        staff = []
    if not staff:   # template unreachable/reshaped: keep last week's staff
        staff = (previous or {}).get("coaches", [])
    for c in staff:
        c["id"] = c.get("id") or f"coach-{name_key(c['name'])}"
        people[c["id"]] = {"id": c["id"], "kind": "coach", "name": c["name"],
                           "title": c["title"], "side": c["side"]}

    def add_career(person: dict) -> None:
        old = prev_people.get(person["id"], {})
        # Carry a career over only while it still ends "…, DEN, present": a new
        # arrival whose article hadn't caught up yet gets re-read next week.
        last = (old.get("stints") or [{}])[-1]
        if last.get("team") == _TEAM and last.get("end") is None:
            career = {k: old.get(k) for k in ("wiki", "stints", "wiki_draft")}
        else:
            hint = dict(overrides)
            staff_wiki = next((c.get("wiki") for c in staff if c["id"] == person["id"]), None)
            if staff_wiki and person["name"] not in hint.get("wiki_titles", {}):
                hint = {**overrides, "wiki_titles": {**overrides.get("wiki_titles", {}),
                                                     person["name"]: staff_wiki}}
            career = _career_from_wiki(person["name"], person["kind"], hint)
        person.update(career)

    say("career histories")
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(add_career, people.values()))

    return {
        "version": _SNAPSHOT_VERSION,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "season": season,
        "chart": chart,
        "coaches": [{k: c[k] for k in ("id", "name", "title", "side")} for c in staff],
        "people": people,
    }


def most_recent_tuesday(now: datetime) -> datetime:
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_of_day - timedelta(days=(now.weekday() - 1) % 7)


def is_stale(snapshot: dict | None, now: datetime | None = None) -> bool:
    if not snapshot or snapshot.get("version") != _SNAPSHOT_VERSION:
        return True
    now = now or datetime.now()
    try:
        return datetime.fromisoformat(snapshot["fetched_at"]) < most_recent_tuesday(now)
    except (KeyError, ValueError):
        return True


def _read(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write(path: str, snapshot: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def load_snapshot(refresh: bool | None = None) -> dict:
    """The snapshot to study from. `refresh`: True forces a refetch, False
    forbids one (tests, offline), None refetches only when stale."""
    cached, seed = _read(_CACHE_PATH), _read(_SEED_PATH)
    # A seed newer than the cache means the repo was updated past this machine.
    current = max((s for s in (cached, seed) if s),
                  key=lambda s: s.get("fetched_at", ""), default=None)
    if refresh is False or (refresh is None and not is_stale(current)):
        if current is None:
            raise RuntimeError("no broncos snapshot; run once with --refresh while online")
        return current
    try:
        sys.stderr.write("refreshing Broncos roster…\n")
        fresh = fetch_snapshot(current)
        _write(_CACHE_PATH, fresh)
        return fresh
    except Exception as e:
        if current is None:
            raise RuntimeError(f"could not fetch the Broncos roster ({e}); "
                               "try again online: uv run python anki-cli.py broncos --refresh")
        sys.stderr.write(f"roster refresh failed ({e}); using snapshot from "
                         f"{current.get('fetched_at', '?')[:10]}\n")
        return current


if __name__ == "__main__":
    # Maintainer entry point: refetch everything (ignoring carried-over careers
    # with --full) and rewrite the committed seed.
    #   uv run python src/broncos/AcBroncosData.py [--full]
    prev = None if "--full" in sys.argv else (_read(_CACHE_PATH) or _read(_SEED_PATH))
    snap = fetch_snapshot(prev, progress=lambda m: print(f"  fetching {m}…"))
    _write(_CACHE_PATH, snap)
    _write(_SEED_PATH, snap)
    curated = load_overrides().get("stints", {})
    missing = [p["name"] for p in snap["people"].values()
               if not p.get("stints") and p["name"] not in curated]
    print(f"{len(snap['people'])} people; no career history for: {', '.join(missing) or 'nobody'}")
