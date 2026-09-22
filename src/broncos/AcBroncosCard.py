"""One cloze card about one Bronco: the main line with a single fact hidden.

    #21 Riley Moss, RCB (O)                                     $3.7m (2023 3.83)

Players get three cards (variant "pos", "num", "name"); coaches have no number
and get two ("title", "name"). Whatever is hidden shows as ?? and everything
else on the line is the cue. The right-hand annotation and the status tag are
context only — never quizzed, and free to change without touching learning.

Answer strictness differs by fact on purpose: a slot must be typed exactly
(RCB2 — the depth digit is the point for a backup; a starter's "1" may be
dropped, so QB passes for QB1, and QB is how a starter's slot is shown), a
number exactly, a name as the full name or the surname with typos forgiven
(cards.textMatch.person_name_match).

The card plugs into the study loop's cloze hooks (clue_text / live_context).
live_context is empty: the unit table would give the answer away, so the
career history and then the titled unit table appear only after answering, as
the answer's display text.
"""

from cards.cardAnswer import CardAnswer
from cards.cardPrompt import SimpleTextPrompt
from cards.lineLayout import LINE_WIDTH, justify
from cards.textMatch import person_name_match, name_tokens

_GREEN = "\033[92m"
_RED   = "\033[91m"
_DIM   = "\033[2m"
_RESET = "\033[0m"

_BLANK = "??"
_NAME_THRESHOLD_S = 10   # typing a full name takes a while; slots/numbers don't
_FACT_THRESHOLD_S = 5


class AcBroncosAnswer(CardAnswer):
    def __init__(self, card_id: str, variant: str, person, roster):
        super().__init__(card_id)
        self.variant = variant
        self._person = person
        self._roster = roster

    def accepted(self) -> list[str]:
        p = self._person
        return {"pos": p.slots, "title": [p.title], "num": [p.jersey], "name": [p.name]}[self.variant]

    def isCorrect(self, answer: str) -> bool:
        a = answer.strip()
        if self.variant == "name":
            return person_name_match(a, self._person.name)
        if self.variant == "num":
            return a.lstrip("#").strip() == self._person.jersey
        typed = a.upper().replace(" ", "")
        return typed in self.accepted() or (self.variant == "pos" and typed in self._person.slot_aliases)

    def isValid(self, answer: str) -> bool:
        """A jersey number that isn't a number is a slip of the fingers, not a
        wrong answer worth an Again."""
        if self.variant == "num":
            return answer.strip().lstrip("#").strip().isdigit()
        return True

    def getInvalidFeedback(self, submitted: str) -> str:
        return "  type the jersey number"

    def getWrongAnswerFeedback(self, submitted: str) -> str:
        return ""   # the revealed main line already shows the right answer in red

    def getDisplayText(self) -> str:
        return (self._roster.history(self._person) + "\n\n"
                + self._roster.titled_table(self._person))

    def getDisplayTextWhenCorrect(self) -> str:
        return self.getDisplayText()

    def getDisplayTextWhenIncorrect(self) -> str:
        return self.getDisplayText()


class AcBroncosCard:
    def __init__(self, person, variant: str, roster):
        self.id = f"{person.id}-{variant}"
        self.variant = variant
        self._person = person
        self._roster = roster
        self._answer = AcBroncosAnswer(self.id, variant, person, roster)

    @property
    def answer_key(self) -> str:
        """Fingerprint of the accepted answer. AcScheduler forgets a card's
        learning when this changes between sessions (a new number, a move up
        the depth chart); cue-only changes such as salary leave it alone."""
        if self.variant == "name":
            return " ".join(name_tokens(self._person.name))
        return "/".join(sorted(self._answer.accepted()))

    @property
    def rating_time_threshold_s(self) -> int:
        return _NAME_THRESHOLD_S if self.variant == "name" else _FACT_THRESHOLD_S

    def _fact(self, variant: str, text: str, guess: str | None, revealed: bool) -> str:
        if variant != self.variant:
            return text
        if not revealed:
            return _BLANK
        color = _GREEN if guess and self.isCorrect(guess) else _RED
        return f"{color}{text}{_RESET}"

    def clue_text(self, guess: str | None = None, revealed: bool = False) -> str:
        p = self._person
        name = self._fact("name", p.name, guess, revealed)
        if p.kind == "coach":
            left = f"{name}, {self._fact('title', p.title, guess, revealed)}"
        else:
            num = self._fact("num", p.jersey, guess, revealed)
            pos = self._fact("pos", "/".join(p.shown_slots), guess, revealed)
            left = f"#{num} {name}, {pos}"
            if p.status:
                left += f" {_DIM}({p.status}){_RESET}"
        return justify(left, self._roster.annotation(p), LINE_WIDTH)

    def live_context(self) -> str:
        return ""

    def getPrompt(self):
        return SimpleTextPrompt(self.id, self.clue_text())

    def getAnswer(self):
        return self._answer

    def isCorrect(self, answer: str) -> bool:
        return self._answer.isCorrect(answer)
