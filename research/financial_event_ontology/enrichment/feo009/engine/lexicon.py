"""Lexical resources loaded from rules/lexicon. Matching is deterministic."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from engine.paths import lexicon_dir

_APOSTROPHES = ("\u2019", "\u2018", "`")


def normalise(text: str | None) -> str:
    if not text:
        return ""
    value = str(text).lower()
    for mark in _APOSTROPHES:
        value = value.replace(mark, "'")
    value = re.sub(r"[^\w\s.'$%&-]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _longest_first(phrases: list[str]) -> list[str]:
    cleaned = [normalise(item) for item in phrases if normalise(item)]
    return sorted(set(cleaned), key=len, reverse=True)


def contains_phrase(text: str, phrase: str) -> bool:
    surface = normalise(text)
    needle = normalise(phrase)
    if not surface or not needle:
        return False
    pattern = r"(?<!\w)" + re.escape(needle) + r"(?!\w)"
    return re.search(pattern, surface) is not None


def first_phrase(text: str, phrases: list[str]) -> str:
    for phrase in _longest_first(phrases):
        if contains_phrase(text, phrase):
            return phrase
    return ""


class Lexicon:
    def __init__(self, tables: dict[str, dict]):
        self.tables = tables

    def table(self, name: str) -> dict:
        return self.tables.get(name) or {}

    def phrases(self, table: str, key: str) -> list[str]:
        return list(self.table(table).get(key) or [])

    def match(self, text: str, table: str, key: str) -> str:
        return first_phrase(text, self.phrases(table, key))

    def index_name(self, text: str) -> str:
        return self.match(text, "market_index", "controlled_names")

    def index_descriptor(self, text: str) -> str:
        return self.match(text, "market_index", "descriptors")

    def exchange_name(self, text: str) -> str:
        return self.match(text, "market_index", "exchanges_not_indices")

    def equity_aggregate(self, text: str) -> str:
        if self.index_descriptor(text) == "stock market index" or contains_phrase(text, "stock market index"):
            return ""
        return self.match(text, "equity_market", "aggregate_phrases")

    def bare_market(self, text: str) -> bool:
        surface = normalise(text)
        if not surface or self.equity_aggregate(text) or self.index_name(text) or self.index_descriptor(text):
            return False
        return surface in {normalise(item) for item in self.phrases("equity_market", "bare_market")}

    def geographic_alone(self, text: str) -> bool:
        surface = normalise(text)
        if not surface or self.equity_aggregate(text) or self.index_name(text):
            return False
        names = {normalise(item) for item in self.phrases("equity_market", "geographic_names")}
        return surface in names

    def central_bank_name(self, text: str) -> str:
        if self.central_bank_collective(text):
            return ""
        return self.match(text, "central_bank", "controlled_names")

    def central_bank_collective(self, text: str) -> str:
        return self.match(text, "central_bank", "collective_expressions")

    def commercial_bank_name(self, text: str) -> str:
        if self.held_out_bank(text) or self.commercial_collective(text):
            return ""
        return self.match(text, "commercial_bank", "controlled_names")

    def commercial_collective(self, text: str) -> str:
        return self.match(text, "commercial_bank", "collective_expressions")

    def held_out_bank(self, text: str) -> str:
        return self.match(text, "commercial_bank", "excluded_names")

    def insurer(self, text: str) -> str:
        return self.match(text, "commercial_bank", "insurer_cues")

    def currency_name(self, text: str) -> str:
        return self.match(text, "currency", "controlled_names")

    def amount_cue(self, text: str) -> str:
        return self.match(text, "currency", "amount_cues")

    def share_unambiguous(self, text: str) -> str:
        return self.match(text, "equity_share", "unambiguous_cues")

    def share_ambiguous(self, text: str) -> str:
        return self.match(text, "equity_share", "ambiguous_cues")

    def system_phrase(self, text: str) -> str:
        return self.match(text, "system_sector", "system_phrases")

    def sector_phrase(self, text: str) -> str:
        return self.match(text, "system_sector", "sector_phrases")

    def system_sector_ambiguous(self, text: str) -> str:
        return self.match(text, "system_sector", "ambiguous_phrases")

    def change_expression(self, text: str) -> str:
        return self.match(text, "change_and_direction", "change_expressions")

    def upward(self, text: str) -> str:
        return self.match(text, "change_and_direction", "upward")

    def downward(self, text: str) -> str:
        return self.match(text, "change_and_direction", "downward")

    def dated_index_descriptor(self, evidence: str, index_surface: str) -> bool:
        """Weekday immediately before an index mention, not a later time adverbial."""
        window = normalise(evidence)
        target = normalise(index_surface)
        if not window or not target or not contains_phrase(window, target):
            return False
        weekdays = self.phrases("change_and_direction", "weekdays")
        pattern = (
            r"(?<!\w)("
            + "|".join(re.escape(normalise(day)) for day in weekdays)
            + r")(?:\s+\w+){0,2}\s+"
            + re.escape(target)
            + r"(?!\w)"
        )
        return re.search(pattern, window) is not None


def load_lexicon(directory: Path | None = None) -> Lexicon:
    folder = directory or lexicon_dir()
    tables: dict[str, dict] = {}
    for path in sorted(folder.glob("*.yaml")):
        with path.open(encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
        name = str(payload.get("name") or path.stem)
        tables[name] = payload
    return Lexicon(tables)


@lru_cache(maxsize=1)
def default_lexicon() -> Lexicon:
    return load_lexicon()
