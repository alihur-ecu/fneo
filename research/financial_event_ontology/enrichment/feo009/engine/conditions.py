"""Named condition functions. Rule files select these identifiers.

No rule string is evaluated as code. An unknown identifier is an error.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from engine.lexicon import contains_phrase, normalise

ARG_LABEL_RE = re.compile(r"^(arg\d+|argm([_-].+)?|support)$", re.IGNORECASE)
NUMBER_RE = re.compile(r"^[+-]?(?:\d+|\d+\.\d+|\.\d+)$")
PERCENT_RE = re.compile(
    r"^[+-]?(?:\d+|\d+\.\d+|\.\d+)\s*(?:%|percent)$",
    re.IGNORECASE,
)

EXPERIMENTAL_INFERENCE = {
    "inverse_generated",
    "rule_inferred",
    "closure_derived",
    "model_inferred",
    "reasoner_entailed",
}

ENDPOINT_PAIRS = {
    "precedes": ("Event", "Event"),
    "follows": ("Event", "Event"),
    "simultaneousWith": ("Event", "Event"),
    "occursDuring": ("Event", "TimeEntity"),
    "includes": ("TimeEntity", "Event"),
    "hasEventTime": ("Event", "TimeEntity"),
}


class ConditionError(KeyError):
    """Raised when a rule cites an unknown condition identifier."""


class View:
    def __init__(self, candidate: dict, context, lexicon):
        self.c = candidate
        self.context = context
        self.lex = lexicon
        self.f = candidate.get("features") or {}

    @property
    def kind(self) -> str:
        return self.c.get("candidate_kind") or ""

    def surface(self) -> str:
        parts = [
            self.c.get("trigger_or_lexical_form"),
            self.c.get("textual_evidence"),
            self.c.get("lemma"),
            self.f.get("label"),
            self.f.get("market_surface"),
        ]
        return normalise(" ".join(str(part) for part in parts if part))

    def mention(self) -> str:
        return normalise(
            self.c.get("trigger_or_lexical_form") or self.f.get("label") or ""
        )

    def evidence(self) -> str:
        return str(self.c.get("textual_evidence") or "")

    def flag(self, name: str, default=None):
        if name in self.f:
            return self.f[name]
        return default

    def requested(self) -> str:
        return str(self.f.get("requested_target") or "")

    def generic(self) -> str:
        return str(self.c.get("generic_type") or "").upper()

    def layers(self) -> list[str]:
        return [str(item).upper() for item in (self.f.get("evidence_layers") or [])]

    def relation(self) -> dict:
        return self.c.get("source_temporal_relation") or {}

    def canonical(self) -> str:
        relation = self.relation()
        return str(
            relation.get("canonical_property")
            or relation.get("canonical_fneo_property")
            or self.f.get("canonical_property")
            or ""
        )

    def inference(self) -> str:
        relation = self.relation()
        return str(
            relation.get("inference_status")
            or relation.get("inference")
            or ""
        ).lower()

    def source_kind(self) -> str:
        return str(self.relation().get("source_kind") or "").lower()

    def suppressed(self) -> bool:
        relation = self.relation()
        status = str(relation.get("suppression_status") or "").lower()
        return bool(relation.get("suppressed")) or status in {"suppressed", "suppressed_or_active"}

    def proposed(self) -> bool:
        relation = self.relation()
        commitment = str(relation.get("commitment_status") or "").lower()
        return bool(relation.get("proposed")) or commitment == "proposed"

    def committed(self) -> bool:
        relation = self.relation()
        if relation.get("committed") is True:
            return True
        return str(relation.get("commitment_status") or "").lower() == "committed"

    def active(self) -> bool:
        relation = self.relation()
        if "active" in relation:
            return bool(relation.get("active"))
        return not self.suppressed()


def _offset_problems(candidate: dict) -> list[str]:
    problems: list[str] = []
    features = candidate.get("features") or {}
    pairs = (
        ("token", candidate.get("token_start"), candidate.get("token_end"), candidate.get("token_boundary_length")),
        (
            "character",
            candidate.get("character_start"),
            candidate.get("character_end"),
            candidate.get("text_boundary_length"),
        ),
    )
    for label, start, end, boundary in pairs:
        if start is None and end is None:
            continue
        if start is None or end is None:
            problems.append(label + "_incomplete")
            continue
        if not isinstance(start, int) or not isinstance(end, int):
            problems.append(label + "_not_integer")
            continue
        if start < 0 or end < 0:
            problems.append(label + "_negative")
        if end <= start:
            problems.append(label + "_not_half_open")
        if isinstance(boundary, int) and end > boundary:
            problems.append(label + "_outside_boundary")
    if features.get("claims_character_evidence"):
        start = candidate.get("character_start")
        end = candidate.get("character_end")
        if not isinstance(start, int) or not isinstance(end, int) or end <= start or start < 0:
            problems.append("character_claim_without_span")
    return problems


def _looks_like_market_change(view: View) -> bool:
    if view.kind != "event_candidate":
        return False
    if view.flag("market_change_candidate") or view.requested() == "MarketChangeEvent":
        return True
    if view.flag("change_expression") is True:
        return True
    return bool(view.lex.change_expression(view.mention()) or view.lex.change_expression(view.evidence()))


def _directions(view: View) -> set[str]:
    if view.flag("direction") == "omit":
        return set()
    listed = view.flag("direction_cues")
    cues: set[str] = set()
    if listed is not None:
        for item in listed:
            token = str(item).lower()
            if token in {"up", "upward"}:
                cues.add("up")
            if token in {"down", "downward"}:
                cues.add("down")
        return cues
    explicit = str(view.flag("direction") or "").lower()
    if explicit in {"up", "upward"}:
        return {"up"}
    if explicit in {"down", "downward"}:
        return {"down"}
    blob = view.mention() + " " + normalise(view.evidence())
    if view.lex.upward(blob):
        cues.add("up")
    if view.lex.downward(blob):
        cues.add("down")
    return cues


def _parse_decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _percentage_points(lexical: str) -> Decimal | None:
    text = normalise(lexical).replace(" ", "")
    if text.endswith("percent"):
        text = text[: -len("percent")]
    if text.endswith("%"):
        text = text[:-1]
    if not NUMBER_RE.match(text):
        return None
    return _parse_decimal(text)


def _source_role(view: View) -> str:
    roles = view.c.get("source_roles") or []
    if roles:
        return str(roles[0])
    return str(view.flag("source_role") or "")


def _role_label_only_shape(label: str) -> bool:
    return bool(label) and bool(ARG_LABEL_RE.match(label.strip()))


def _distinct_ids(view: View) -> list:
    return list(view.flag("distinct_mention_ids") or [])


def _reviewer(view: View) -> bool:
    return view.flag("reviewer_decision") == "accepted" or view.flag("reviewer_accepted") is True


def _market_id(view: View) -> str:
    return str(view.flag("market_candidate_id") or "")


def _event_id(view: View) -> str:
    return str(view.flag("event_candidate_id") or view.c.get("candidate_id") or "")


# --- evidence and document -------------------------------------------------


def document_present(view: View) -> bool:
    return bool(view.c.get("document_id"))


def missing_document(view: View) -> bool:
    return not document_present(view)


def textual_evidence_present(view: View) -> bool:
    if view.evidence().strip():
        return True
    if view.c.get("trigger_or_lexical_form"):
        return True
    if view.flag("traceable") is True:
        return True
    return False


def invalid_offset(view: View) -> bool:
    return bool(_offset_problems(view.c))


def half_open_span(view: View) -> bool:
    return not invalid_offset(view)


def valid_evidence_span(view: View) -> bool:
    if missing_document(view) or invalid_offset(view):
        return False
    token_ok = isinstance(view.c.get("token_start"), int) and isinstance(view.c.get("token_end"), int)
    character_ok = isinstance(view.c.get("character_start"), int) and isinstance(view.c.get("character_end"), int)
    if view.flag("claims_character_evidence") and not character_ok:
        return False
    if token_ok or character_ok or view.flag("traceable") is True:
        return True
    return textual_evidence_present(view)


def token_evidence_when_character_absent(view: View) -> bool:
    if view.c.get("character_start") is not None:
        return False
    return isinstance(view.c.get("token_start"), int) and isinstance(view.c.get("token_end"), int)


def negative_character_evidence_without_offsets(view: View) -> bool:
    return "character_claim_without_span" in _offset_problems(view.c)


def structural_mention_present(view: View) -> bool:
    return bool(view.c.get("trigger_or_lexical_form") or view.f.get("label"))


# --- shared entity cues ----------------------------------------------------


def reviewer_accepted_decision(view: View) -> bool:
    return _reviewer(view)


def controlled_name_match(view: View) -> bool:
    surface = view.surface()
    return bool(
        view.lex.index_name(surface)
        or view.lex.central_bank_name(surface)
        or view.lex.commercial_bank_name(surface)
        or view.lex.currency_name(surface)
    )


def controlled_name_or_reviewer_decision(view: View) -> bool:
    return controlled_name_match(view) or _reviewer(view)


def explicit_descriptor(view: View) -> bool:
    surface = view.surface()
    return bool(
        view.lex.index_descriptor(surface)
        or view.lex.equity_aggregate(surface)
        or contains_phrase(surface, "central bank")
        or contains_phrase(surface, "shares")
        or contains_phrase(surface, "share")
    )


def index_context(view: View) -> bool:
    surface = view.mention() or view.surface()
    if view.lex.exchange_name(surface) and not view.lex.index_name(surface):
        return False
    if view.lex.index_name(surface):
        return True
    if view.lex.index_descriptor(view.mention()):
        return True
    return False


def equity_market_context(view: View) -> bool:
    surface = view.mention() or view.surface()
    if contains_phrase(surface, "stock market index"):
        return False
    return bool(view.lex.equity_aggregate(surface))


def organisation_context(view: View) -> bool:
    if view.flag("contextual_evidence") is True or view.flag("contextual_organisation") is True:
        return True
    surface = view.surface()
    return bool(
        view.lex.central_bank_name(surface)
        or view.lex.commercial_bank_name(surface)
        or view.lex.central_bank_collective(surface)
        or contains_phrase(surface, "bank")
        or contains_phrase(surface, "reserve")
    )


def negative_issuing_company(view: View) -> bool:
    surface = view.mention()
    if view.lex.index_name(surface) or view.lex.index_descriptor(surface):
        return False
    return bool(view.lex.match(surface, "market_index", "issuing_company_cues"))


def negative_exchange_not_index(view: View) -> bool:
    surface = view.mention() or view.surface()
    exchange = view.lex.exchange_name(surface)
    if not exchange:
        return False
    # A longer exchange phrase blocks an embedded index token such as Nasdaq.
    return True


def negative_generic_market(view: View) -> bool:
    surface = view.mention()
    if view.lex.index_name(surface) or index_context(view):
        return False
    return view.lex.bare_market(surface) or (
        contains_phrase(surface, "market") and not view.lex.index_descriptor(surface)
    )


def negative_numeric_level_as_entity(view: View) -> bool:
    surface = view.mention()
    if not surface:
        return False
    if view.lex.index_name(surface):
        return False
    if NUMBER_RE.match(surface):
        return True
    return surface in {"index level", "the index level", "points"}


def negative_unrelated_acronym(view: View) -> bool:
    surface = view.mention()
    if view.lex.index_name(surface):
        return False
    return bool(view.lex.match(surface, "market_index", "unrelated_acronyms"))


def negative_fin_code_only(view: View) -> bool:
    if view.generic() != "FIN":
        return False
    if controlled_name_match(view) or index_context(view) or equity_market_context(view) or _reviewer(view):
        return False
    return True


def negative_equity_market_reading(view: View) -> bool:
    if view.requested() == "EquityMarket":
        return True
    surface = view.mention()
    if view.lex.index_name(surface) or view.lex.index_descriptor(surface):
        return False
    return bool(view.lex.equity_aggregate(surface))


def negative_index_reading(view: View) -> bool:
    surface = view.mention()
    if view.requested() == "MarketIndex":
        return True
    if contains_phrase(surface, "stock market index"):
        return True
    if view.lex.index_name(surface):
        return True
    return view.lex.index_descriptor(surface) == "index" and not view.lex.equity_aggregate(surface)


def negative_bare_market(view: View) -> bool:
    surface = view.mention()
    if equity_market_context(view):
        return False
    return view.lex.bare_market(surface) or surface in {"market", "the market", "markets"}


def negative_geographic_name_alone(view: View) -> bool:
    return view.lex.geographic_alone(view.mention())


def negative_individual_company(view: View) -> bool:
    surface = view.mention()
    if equity_market_context(view) or view.lex.index_name(surface):
        return False
    return bool(view.lex.match(surface, "equity_share", "organisation_cues")) and not equity_market_context(view)


def negative_physical_marketplace(view: View) -> bool:
    return bool(view.lex.match(view.mention(), "equity_market", "physical_marketplace_cues")) or bool(
        view.lex.exchange_name(view.mention())
    )


def negative_same_individual_as_index(view: View) -> bool:
    return bool(view.lex.index_name(view.mention())) and view.requested() == "EquityMarket"


def conjunction_without_distinct_mentions(view: View) -> bool:
    if view.flag("distinct_mentions_provided") is True and len(_distinct_ids(view)) >= 2:
        return False
    if len(_distinct_ids(view)) >= 2:
        return False
    return bool(view.flag("conjunction") or view.flag("collective_mention") or view.flag("collective_market"))


def collective_mention(view: View) -> bool:
    surface = view.surface()
    return bool(
        view.flag("collective_mention")
        or view.flag("collective_market")
        or view.lex.central_bank_collective(surface)
        or view.lex.commercial_collective(surface)
    )


def generic_org_without_context(view: View) -> bool:
    if view.generic() != "ORG":
        return False
    if organisation_context(view) and (
        controlled_name_match(view) or _reviewer(view) or view.lex.commercial_bank_name(view.surface())
    ):
        return False
    if view.lex.central_bank_name(view.surface()) or view.lex.commercial_bank_name(view.surface()):
        return False
    return True


def negative_org_code_only(view: View) -> bool:
    return generic_org_without_context(view) and not _reviewer(view)


def negative_funding_verb_types_bank(view: View) -> bool:
    if view.lex.central_bank_name(view.mention()):
        return False
    return bool(view.lex.match(view.mention(), "central_bank", "funding_verbs")) and not view.lex.central_bank_name(
        view.surface()
    )


def negative_acting_central_bank_role(view: View) -> bool:
    return bool(view.flag("invent_acting_role"))


def negative_collective_as_extra_institution(view: View) -> bool:
    return bool(view.flag("count_collective_as_extra_institution"))


def negative_held_out_commercial_bank(view: View) -> bool:
    return bool(view.lex.held_out_bank(view.surface()))


def negative_central_bank_name_as_commercial(view: View) -> bool:
    return bool(view.lex.central_bank_name(view.mention()) or view.lex.central_bank_collective(view.mention()))


def negative_insurer(view: View) -> bool:
    return bool(view.lex.insurer(view.surface()))


def novel_bank_like_name(view: View) -> bool:
    surface = view.surface()
    if (
        view.lex.commercial_bank_name(surface)
        or view.lex.commercial_collective(surface)
        or view.lex.held_out_bank(surface)
        or view.lex.central_bank_name(surface)
        or view.lex.insurer(surface)
        or _reviewer(view)
    ):
        return False
    return contains_phrase(surface, "bank") or contains_phrase(surface, "lender")


def negative_generic_bank_word(view: View) -> bool:
    return novel_bank_like_name(view)


def negative_amount_is_currency(view: View) -> bool:
    if view.flag("amount_reading") is True and not view.lex.currency_name(view.mention()):
        return True
    surface = view.mention()
    if view.lex.currency_name(surface) and not view.lex.amount_cue(surface):
        return False
    return bool(view.lex.amount_cue(surface)) and not view.lex.currency_name(surface)


def amount_in_span(view: View) -> bool:
    if view.flag("amount_in_span") is True or view.flag("amount_reading") is True:
        return bool(view.lex.currency_name(view.surface()) or _reviewer(view) or view.requested() == "Currency")
    return bool(view.lex.currency_name(view.surface()) and view.lex.amount_cue(view.surface()))


def negative_currency_code_creates_currency(view: View) -> bool:
    return bool(view.flag("currency_code_as_currency_individual"))


def currency_name_not_amount(view: View) -> bool:
    if negative_amount_is_currency(view):
        return False
    if _reviewer(view) and view.flag("amount_reading") is not True:
        return True
    return bool(view.lex.currency_name(view.mention())) and not amount_in_span(view)


def share_context_unambiguous(view: View) -> bool:
    if view.flag("double_typed"):
        return False
    return bool(view.lex.share_unambiguous(view.mention()))


def negative_company_name_as_share(view: View) -> bool:
    surface = view.mention()
    if view.lex.share_unambiguous(surface):
        return False
    return bool(view.lex.match(surface, "equity_share", "organisation_cues")) or (
        view.lex.commercial_bank_name(surface) and not view.lex.share_unambiguous(surface)
    )


def negative_share_as_company(view: View) -> bool:
    return bool(view.flag("share_typed_as_company"))


def negative_double_typed_span(view: View) -> bool:
    return bool(view.flag("double_typed"))


def negative_forced_system_sector_classification(view: View) -> bool:
    """Automatic system or sector typing is the blocked outcome."""
    return True


def negative_factuality_as_requirement(view: View) -> bool:
    return bool(view.flag("factuality_only"))


def not_financial_target(view: View) -> bool:
    requested = view.requested()
    return requested in {"", "Entity", "Event", "TimeEntity"}


# --- applicability: entities ----------------------------------------------


def applies_market_index(view: View) -> bool:
    if view.kind != "entity_candidate" or view.requested() == "EquityMarket":
        return False
    if view.requested() == "MarketIndex":
        return True
    surface = view.mention()
    if view.lex.exchange_name(surface):
        return True
    if negative_numeric_level_as_entity(view) or negative_unrelated_acronym(view):
        return True
    return bool(view.lex.index_name(surface) or view.lex.index_descriptor(surface))


def applies_equity_market(view: View) -> bool:
    if view.kind != "entity_candidate" or view.requested() == "MarketIndex":
        return False
    if view.requested() == "EquityMarket":
        return True
    surface = view.mention()
    if view.lex.equity_aggregate(surface) or view.lex.bare_market(surface) or view.lex.geographic_alone(surface):
        return True
    return negative_physical_marketplace(view) and view.requested() == "EquityMarket"


def applies_central_bank(view: View) -> bool:
    if view.kind != "entity_candidate":
        return False
    if view.requested() == "CentralBank":
        return True
    surface = view.surface()
    return bool(view.lex.central_bank_name(surface) or view.lex.central_bank_collective(surface))


def applies_commercial_bank(view: View) -> bool:
    if view.kind != "entity_candidate":
        return False
    surface = view.surface()
    if view.lex.central_bank_name(surface) and view.requested() != "CommercialBank":
        return False
    if view.requested() == "CommercialBank":
        return True
    if view.lex.commercial_bank_name(surface) or view.lex.commercial_collective(surface) or view.lex.held_out_bank(surface):
        return True
    if view.lex.insurer(surface):
        return True
    return novel_bank_like_name(view)


def applies_currency(view: View) -> bool:
    if view.kind != "entity_candidate":
        return False
    if view.requested() == "Currency":
        return True
    return bool(view.lex.currency_name(view.surface()))


def applies_equity_share(view: View) -> bool:
    if view.kind != "entity_candidate":
        return False
    if view.requested() == "EquityShare":
        return True
    return bool(view.lex.share_unambiguous(view.mention()) or view.lex.share_ambiguous(view.mention()))


def applies_financial_system(view: View) -> bool:
    if view.kind != "entity_candidate":
        return False
    competing = view.flag("competing_targets") or []
    surface = view.surface()
    return bool(
        view.requested() == "FinancialSystem"
        or "FinancialSystem" in competing
        or view.lex.system_phrase(surface)
        or view.lex.system_sector_ambiguous(surface)
    )


def applies_financial_sector(view: View) -> bool:
    if view.kind != "entity_candidate":
        return False
    competing = view.flag("competing_targets") or []
    surface = view.surface()
    return bool(
        view.requested() == "FinancialSector"
        or "FinancialSector" in competing
        or view.lex.sector_phrase(surface)
        or view.lex.system_sector_ambiguous(surface)
    )


def applies_generic_entity(view: View) -> bool:
    return view.kind == "entity_candidate" and not view.flag("unmapped")


def applies_generic_event(view: View) -> bool:
    return view.kind == "event_candidate" and not view.flag("unmapped")


def applies_time_entity(view: View) -> bool:
    return view.kind == "temporal_candidate" and bool(view.flag("time_mention")) and not view.canonical()


# --- market change ---------------------------------------------------------


def change_expression(view: View) -> bool:
    explicit = view.flag("change_expression")
    if explicit is True:
        return True
    if explicit is False:
        return False
    return bool(view.lex.change_expression(view.mention()) or view.lex.change_expression(view.evidence()))


def accepted_market_referent(view: View) -> bool:
    market_id = _market_id(view)
    if not market_id or view.context is None:
        return False
    return view.context.accepted_any(market_id, ("MarketIndex", "EquityMarket"))


def contextual_attachment(view: View) -> bool:
    if view.flag("contextual_attachment") is True:
        return True
    if view.flag("contextual_attachment") is False or view.flag("ambiguous_attachment") is True:
        return False
    return "EVENT_PARTICIPANT" in view.layers() and bool(_market_id(view))


def source_event_mention(view: View) -> bool:
    if view.kind == "event_candidate" and (view.c.get("trigger_or_lexical_form") or view.c.get("source_mention_ids")):
        return True
    return bool(view.c.get("source_annotation_ids") or view.flag("source_event"))


def blocking_ambiguity(view: View) -> bool:
    return bool(view.flag("blocking_ambiguity") or view.flag("ambiguous_attachment") or view.flag("frame_disagreement"))


def sensitivity_set_marker(view: View) -> bool:
    if view.flag("sensitivity_set") or view.flag("dated_descriptor") or view.flag("dated_descriptor_outside_primary"):
        return True
    return view.lex.dated_index_descriptor(view.evidence(), str(view.flag("market_surface") or view.flag("label") or ""))


def dated_descriptor_marker(view: View) -> bool:
    return bool(view.flag("dated_descriptor") or view.flag("dated_descriptor_outside_primary")) or view.lex.dated_index_descriptor(
        view.evidence(), str(view.flag("market_surface") or "")
    )


def negative_trigger_only(view: View) -> bool:
    if view.flag("trigger_only") is True:
        return True
    return bool(view.flag("trigger_only"))


def negative_other_code_only(view: View) -> bool:
    return view.flag("other_code_only") is True


def negative_currency_or_value_participant_without_market(view: View) -> bool:
    if view.flag("currency_not_market") or view.flag("value_not_market"):
        return True
    return str(view.flag("referent_kind") or "") in {
        "Currency",
        "MonetaryAmount",
        "NumericalValue",
        "PercentageValue",
    }


def negative_automatic_promotion_of_sensitivity(view: View) -> bool:
    return sensitivity_set_marker(view) or bool(view.flag("promote_sensitivity_to_primary"))


def negative_merge_distinct_triggers(view: View) -> bool:
    return bool(view.flag("merge_triggers"))


def negative_collective_cross_document_identity(view: View) -> bool:
    return bool(view.flag("cross_document_merge"))


def distinct_triggers(view: View) -> bool:
    return bool(view.flag("distinct_triggers_in_sentence")) and not view.flag("shared_unresolved_trigger")


def shared_unresolved_trigger(view: View) -> bool:
    return bool(view.flag("shared_unresolved_trigger"))


def applies_mce_currency_scope(view: View) -> bool:
    return _looks_like_market_change(view) and negative_currency_or_value_participant_without_market(view)


def applies_mce_trigger_only(view: View) -> bool:
    return view.kind == "event_candidate" and (negative_trigger_only(view) or negative_other_code_only(view))


def applies_mce_sensitivity(view: View) -> bool:
    return _looks_like_market_change(view) and sensitivity_set_marker(view)


def applies_mce_conjunction(view: View) -> bool:
    return _looks_like_market_change(view) and conjunction_without_distinct_mentions(view)


def applies_mce_distinct_triggers(view: View) -> bool:
    return _looks_like_market_change(view) and (
        distinct_triggers(view) or shared_unresolved_trigger(view)
    )


def applies_mce_strict(view: View) -> bool:
    return _looks_like_market_change(view)


# --- direction -------------------------------------------------------------


def direction_cue_present(view: View) -> bool:
    return bool(_directions(view))


def direction_up(view: View) -> bool:
    return _directions(view) == {"up"}


def direction_down(view: View) -> bool:
    return _directions(view) == {"down"}


def conflicting_direction_same_event(view: View) -> bool:
    return _directions(view) == {"up", "down"} and not view.flag("distinct_event_for_each_direction")


def applies_direction(view: View) -> bool:
    """Direction is optional and is considered only for an accepted market-change event."""
    if view.kind != "event_candidate" or view.flag("direction") == "omit":
        return False
    if not direction_cue_present(view):
        return False
    return accepted_market_change_for_direction(view)


def accepted_market_change_for_direction(view: View) -> bool:
    if view.context is None:
        return False
    return view.context.accepted(view.c.get("candidate_id"), "MarketChangeEvent")


# --- affected market -------------------------------------------------------


def event_participant_primary(view: View) -> bool:
    if "EVENT_PARTICIPANT" in view.layers():
        return True
    return bool(view.flag("approved_equivalent_participant"))


def frame_argument_support_only(view: View) -> bool:
    return "HAS_FRAME_ARGUMENT" in view.layers() and "EVENT_PARTICIPANT" not in view.layers()


def legacy_participant_diagnostic_only(view: View) -> bool:
    return "PARTICIPANT" in view.layers() and "EVENT_PARTICIPANT" not in view.layers() and not view.flag(
        "approved_equivalent_participant"
    )


def arg_label_alone(view: View) -> bool:
    if view.flag("arg_label_only") is True:
        return True
    if contextual_attachment(view) or event_participant_primary(view):
        return False
    if view.flag("ambiguous_attachment") or "HAS_FRAME_ARGUMENT" in view.layers() or "PARTICIPANT" in view.layers():
        return False
    return _role_label_only_shape(_source_role(view))


def negative_arg_label_promotes_role(view: View) -> bool:
    return arg_label_alone(view)


def negative_invented_source_role(view: View) -> bool:
    return bool(view.flag("invented_source_role"))


def missing_source_role(view: View) -> bool:
    return not _source_role(view)


def primary_participant_or_approved_equivalent(view: View) -> bool:
    return event_participant_primary(view)


def accepted_market_change_event(view: View) -> bool:
    if view.context is None:
        return False
    return view.context.accepted(_event_id(view), "MarketChangeEvent")


def multiple_markets_explicit(view: View) -> bool:
    return bool(view.flag("multiple_markets")) and contextual_attachment(view) and not conjunction_without_distinct_mentions(
        view
    )


def multiple_events_one_market(view: View) -> bool:
    return bool(view.flag("multiple_events_one_market")) and contextual_attachment(view)


def _affected_intent(view: View) -> bool:
    if view.kind != "participation_candidate":
        return False
    predicate = str(view.flag("predicate") or "")
    if predicate == "hasParticipant":
        return False
    return bool(view.flag("affected_market") or predicate == "hasAffectedMarket" or _market_id(view))


def applies_aff_arg_only(view: View) -> bool:
    return _affected_intent(view) and arg_label_alone(view)


def applies_aff_collective(view: View) -> bool:
    return _affected_intent(view) and conjunction_without_distinct_mentions(view)


def applies_aff_ambiguous(view: View) -> bool:
    return _affected_intent(view) and (
        blocking_ambiguity(view) or frame_argument_support_only(view) or legacy_participant_diagnostic_only(view)
    )


def applies_aff_multi_market(view: View) -> bool:
    return _affected_intent(view) and multiple_markets_explicit(view)


def applies_aff_multi_event(view: View) -> bool:
    return _affected_intent(view) and multiple_events_one_market(view)


def applies_aff_missing_role(view: View) -> bool:
    return (
        _affected_intent(view)
        and missing_source_role(view)
        and contextual_attachment(view)
        and event_participant_primary(view)
        and not arg_label_alone(view)
    )


def applies_aff_primary(view: View) -> bool:
    return _affected_intent(view)


def applies_generic_participation(view: View) -> bool:
    return view.kind == "participation_candidate" and str(view.flag("predicate") or "") == "hasParticipant"


def explicit_has_participant_relation(view: View) -> bool:
    return applies_generic_participation(view) and view.flag("relation_status") == "accepted"


# --- temporal --------------------------------------------------------------


def _endpoints_match(view: View, canonical: str) -> bool:
    expected = ENDPOINT_PAIRS.get(canonical)
    if expected is None:
        return False
    if view.flag("endpoint_types_valid") is False:
        return False
    relation = view.relation()
    subject = relation.get("subject_endpoint_type") or view.flag("subject_endpoint_type")
    object_ = relation.get("object_endpoint_type") or view.flag("object_endpoint_type")
    if subject is None and object_ is None:
        return view.flag("endpoint_types_valid") is not False
    return (subject, object_) == expected


def negative_wrong_temporal_endpoint(view: View) -> bool:
    canonical = view.canonical() or ("hasEventTime" if view.flag("event_time") else "")
    if not canonical:
        return False
    return not _endpoints_match(view, canonical)


def explicit_inference(view: View) -> bool:
    inference = view.inference()
    return inference in {"", "explicit"} and view.source_kind() not in {
        "inverse_generated",
        "rule_inferred",
        "closure_derived",
        "model_inferred",
        "reasoner_entailed",
    }


def active_committed_nonsuppressed(view: View) -> bool:
    return view.active() and view.committed() and not view.suppressed() and not view.proposed()


def traceable_temporal_evidence(view: View) -> bool:
    if view.flag("traceable") is False:
        return False
    if view.flag("traceable") is True:
        return True
    return textual_evidence_present(view) or bool(view.c.get("source_annotation_ids"))


def explicit_event_time_relation(view: View) -> bool:
    canonical = view.canonical()
    original = str(view.relation().get("original_relation") or view.relation().get("original_label") or "")
    return bool(view.flag("event_time") or canonical == "hasEventTime" or original.upper() in {"HAS_TIME_ANCHOR", "TLINK_TIME"})


def negative_event_ordering_as_event_time(view: View) -> bool:
    return view.canonical() in {"precedes", "follows", "simultaneousWith", "occursDuring", "includes"} and bool(
        view.flag("event_time")
    )


def publication_time_is_not_event_time(view: View) -> bool:
    return bool(view.flag("publication_time_used_as_event_time"))


def canonical_temporal_mapping(view: View) -> bool:
    return view.canonical() in ENDPOINT_PAIRS


def temporal_relation_eligible(view: View) -> bool:
    canonical = view.canonical()
    if canonical not in {"precedes", "follows", "simultaneousWith", "occursDuring", "includes"}:
        return False
    return (
        active_committed_nonsuppressed(view)
        and explicit_inference(view)
        and traceable_temporal_evidence(view)
        and not negative_wrong_temporal_endpoint(view)
        and not view.flag("bucket_total")
    )


def temporal_status_proposed(view: View) -> bool:
    return view.proposed() and not view.suppressed()


def temporal_status_suppressed(view: View) -> bool:
    return view.suppressed()


def reasoner_entailed_inverse(view: View) -> bool:
    return view.inference() == "reasoner_entailed" or view.source_kind() == "reasoner_entailed"


def inverse_generated_relation(view: View) -> bool:
    return view.inference() == "inverse_generated" or view.source_kind() == "inverse_generated"


def rule_inferred_relation(view: View) -> bool:
    return view.inference() == "rule_inferred" or view.source_kind() == "rule_inferred"


def closure_derived_relation(view: View) -> bool:
    return view.inference() == "closure_derived" or view.source_kind() == "closure_derived"


def model_inferred_relation(view: View) -> bool:
    return view.inference() == "model_inferred" or view.source_kind() == "model_inferred"


def negative_reasoner_entailment_as_evidence(view: View) -> bool:
    return reasoner_entailed_inverse(view)


def negative_materialise_ineligible_temporal(view: View) -> bool:
    return (
        view.suppressed()
        or view.proposed()
        or view.inference() in EXPERIMENTAL_INFERENCE
        or view.source_kind() in EXPERIMENTAL_INFERENCE
        or bool(view.flag("bucket_total"))
    )


def negative_bucket_total(view: View) -> bool:
    return bool(view.flag("bucket_total"))


def negative_deferred_temporal_label(view: View) -> bool:
    original = str(view.relation().get("original_relation") or view.relation().get("original_label") or "").upper()
    canonical = view.canonical()
    deferred = {"BEGINS", "BEGINS-ON", "BEGUN_BY", "ENDS", "ENDED_BY", "MEASURE"}
    return canonical in {"begins", "ends", "measure"} or original in deferred or any(
        token in original for token in deferred
    )


def _temporal_attempt(view: View) -> bool:
    return view.kind == "temporal_candidate" and not view.flag("time_mention") and not view.flag("event_time")


def applies_event_time(view: View) -> bool:
    return view.kind == "temporal_candidate" and explicit_event_time_relation(view) and not view.flag("time_mention")


def applies_temporal_bucket(view: View) -> bool:
    return view.kind == "temporal_candidate" and negative_bucket_total(view)


def _deferred_family(view: View) -> str:
    original = str(view.relation().get("original_relation") or view.relation().get("original_label") or "").upper()
    canonical = view.canonical().lower()
    if canonical == "begins" or "BEGIN" in original:
        return "begins"
    if canonical == "ends" or original.startswith("END") or "ENDED_BY" in original:
        return "ends"
    if canonical == "measure" or "MEASURE" in original:
        return "measure"
    return ""


def applies_temporal_deferred(view: View) -> bool:
    return _temporal_attempt(view) and _deferred_family(view) == "begins"


def applies_temporal_ends(view: View) -> bool:
    return _temporal_attempt(view) and _deferred_family(view) == "ends"


def applies_temporal_measure(view: View) -> bool:
    return _temporal_attempt(view) and _deferred_family(view) == "measure"


def applies_temporal_reasoner(view: View) -> bool:
    return _temporal_attempt(view) and reasoner_entailed_inverse(view)


def applies_temporal_inverse(view: View) -> bool:
    return _temporal_attempt(view) and inverse_generated_relation(view)


def applies_temporal_suppressed(view: View) -> bool:
    return _temporal_attempt(view) and view.suppressed() and not inverse_generated_relation(view)


def applies_temporal_proposed(view: View) -> bool:
    return _temporal_attempt(view) and temporal_status_proposed(view) and not view.suppressed()


def applies_temporal_rule(view: View) -> bool:
    return (
        _temporal_attempt(view)
        and rule_inferred_relation(view)
        and not view.proposed()
        and not view.suppressed()
    )


def applies_temporal_closure(view: View) -> bool:
    return _temporal_attempt(view) and closure_derived_relation(view) and not view.suppressed()


def applies_temporal_model(view: View) -> bool:
    return _temporal_attempt(view) and model_inferred_relation(view) and not view.suppressed()


def _applies_order(view: View, name: str) -> bool:
    if not _temporal_attempt(view) or view.canonical() != name:
        return False
    if view.suppressed() or view.proposed() or view.inference() in EXPERIMENTAL_INFERENCE:
        return False
    if view.source_kind() in EXPERIMENTAL_INFERENCE:
        return False
    return True


def applies_temporal_precedes(view: View) -> bool:
    return _applies_order(view, "precedes")


def applies_temporal_follows(view: View) -> bool:
    return _applies_order(view, "follows")


def applies_temporal_simultaneous(view: View) -> bool:
    return _applies_order(view, "simultaneousWith")


def applies_temporal_during(view: View) -> bool:
    return _applies_order(view, "occursDuring")


def applies_temporal_includes(view: View) -> bool:
    return _applies_order(view, "includes")


# --- values ----------------------------------------------------------------


def _lexical(view: View) -> str:
    return str(
        view.f.get("lexical")
        or view.c.get("trigger_or_lexical_form")
        or ""
    )


def percentage_lexical_preserved(view: View) -> bool:
    lexical = _lexical(view)
    return bool(PERCENT_RE.match(normalise(lexical).replace(" ", "")) or "percent" in lexical.lower() or "%" in lexical)


def value_type_numeric(view: View) -> bool:
    if view.flag("force_fraction"):
        return False
    points = _percentage_points(_lexical(view)) if percentage_lexical_preserved(view) else None
    if points is not None:
        return True
    return _parse_decimal(view.f.get("numerical_value") if view.f.get("numerical_value") is not None else _lexical(view)) is not None


def percentage_points_not_fraction(view: View) -> bool:
    if view.flag("force_fraction"):
        return False
    lexical = _lexical(view)
    points = _percentage_points(lexical)
    if points is None:
        return False
    supplied = view.f.get("numerical_value")
    if supplied is None or supplied == "":
        return True
    parsed = _parse_decimal(supplied)
    if parsed is None:
        return False
    if points >= 1 and parsed < 1 and abs(parsed * Decimal(100) - points) < Decimal("0.0001"):
        return False
    return parsed == points


def invalid_percentage_fraction(view: View) -> bool:
    return percentage_lexical_preserved(view) and not percentage_points_not_fraction(view)


def negative_percentage_as_fraction(view: View) -> bool:
    return invalid_percentage_fraction(view)


def value_lexical_present(view: View) -> bool:
    return bool(_lexical(view))


def generic_number(view: View) -> bool:
    if percentage_lexical_preserved(view) or view.flag("value_kind") in {"percentage", "money", "quantity"}:
        return False
    return value_type_numeric(view)


def monetary_amount_components(view: View) -> bool:
    return view.flag("value_kind") == "money" or bool(view.f.get("currency_code"))


def quantity_not_percentage(view: View) -> bool:
    return view.flag("value_kind") == "quantity" and not percentage_lexical_preserved(view)


def co_presence_only_event_value(view: View) -> bool:
    basis = str(view.flag("attachment_basis") or "")
    return basis in {"sentence_copresence", "document_copresence", "token_overlap", "indirect_path"} or bool(
        view.flag("co_presence_only")
    )


def negative_co_presence_attachment(view: View) -> bool:
    return co_presence_only_event_value(view)


def event_value_explicitly_requested(view: View) -> bool:
    return bool(view.flag("event_value_requested"))


def applies_percentage(view: View) -> bool:
    return view.kind == "value_candidate" and not view.flag("event_value_link") and (
        view.flag("value_kind") == "percentage" or percentage_lexical_preserved(view)
    )


def applies_monetary(view: View) -> bool:
    return view.kind == "value_candidate" and not view.flag("event_value_link") and (
        view.flag("value_kind") == "money" or bool(view.f.get("currency_code"))
    )


def applies_quantity(view: View) -> bool:
    return (
        view.kind == "value_candidate"
        and not view.flag("event_value_link")
        and view.flag("value_kind") == "quantity"
    )


def applies_numerical(view: View) -> bool:
    return (
        view.kind == "value_candidate"
        and not view.flag("event_value_link")
        and view.flag("value_kind") in {None, "", "number", "numerical"}
        and not percentage_lexical_preserved(view)
        and not view.f.get("currency_code")
    )


def applies_event_value_link(view: View) -> bool:
    return view.kind == "value_candidate" and bool(view.flag("event_value_link") or view.flag("co_presence_only"))


def applies_literal_value(view: View) -> bool:
    return view.kind == "value_candidate" and bool(view.flag("literal_assertion")) and percentage_lexical_preserved(view)


def applies_evidence_record(view: View) -> bool:
    return view.kind == "evidence_candidate" and not view.flag("unmapped")


def applies_unmapped(view: View) -> bool:
    return bool(view.flag("unmapped"))


def negative_unmapped_metadata(view: View) -> bool:
    return bool(view.flag("unmapped"))


def negative_no_applicable_financial_rule(view: View) -> bool:
    return True


def negative_no_financial_role_from_structural_participation(view: View) -> bool:
    return str(view.flag("predicate") or "") == "hasAffectedMarket"


REGISTRY = {
    "document_present": document_present,
    "missing_document": missing_document,
    "textual_evidence_present": textual_evidence_present,
    "invalid_offset": invalid_offset,
    "half_open_span": half_open_span,
    "valid_evidence_span": valid_evidence_span,
    "token_evidence_when_character_absent": token_evidence_when_character_absent,
    "negative_character_evidence_without_offsets": negative_character_evidence_without_offsets,
    "structural_mention_present": structural_mention_present,
    "reviewer_accepted_decision": reviewer_accepted_decision,
    "controlled_name_match": controlled_name_match,
    "controlled_name_or_reviewer_decision": controlled_name_or_reviewer_decision,
    "explicit_descriptor": explicit_descriptor,
    "index_context": index_context,
    "equity_market_context": equity_market_context,
    "organisation_context": organisation_context,
    "negative_issuing_company": negative_issuing_company,
    "negative_exchange_not_index": negative_exchange_not_index,
    "negative_generic_market": negative_generic_market,
    "negative_numeric_level_as_entity": negative_numeric_level_as_entity,
    "negative_unrelated_acronym": negative_unrelated_acronym,
    "negative_fin_code_only": negative_fin_code_only,
    "negative_equity_market_reading": negative_equity_market_reading,
    "negative_index_reading": negative_index_reading,
    "negative_bare_market": negative_bare_market,
    "negative_geographic_name_alone": negative_geographic_name_alone,
    "negative_individual_company": negative_individual_company,
    "negative_physical_marketplace": negative_physical_marketplace,
    "negative_same_individual_as_index": negative_same_individual_as_index,
    "conjunction_without_distinct_mentions": conjunction_without_distinct_mentions,
    "collective_mention": collective_mention,
    "generic_org_without_context": generic_org_without_context,
    "negative_org_code_only": negative_org_code_only,
    "negative_funding_verb_types_bank": negative_funding_verb_types_bank,
    "negative_acting_central_bank_role": negative_acting_central_bank_role,
    "negative_collective_as_extra_institution": negative_collective_as_extra_institution,
    "negative_held_out_commercial_bank": negative_held_out_commercial_bank,
    "negative_central_bank_name_as_commercial": negative_central_bank_name_as_commercial,
    "negative_insurer": negative_insurer,
    "novel_bank_like_name": novel_bank_like_name,
    "negative_generic_bank_word": negative_generic_bank_word,
    "negative_amount_is_currency": negative_amount_is_currency,
    "amount_in_span": amount_in_span,
    "negative_currency_code_creates_currency": negative_currency_code_creates_currency,
    "currency_name_not_amount": currency_name_not_amount,
    "share_context_unambiguous": share_context_unambiguous,
    "negative_company_name_as_share": negative_company_name_as_share,
    "negative_share_as_company": negative_share_as_company,
    "negative_double_typed_span": negative_double_typed_span,
    "negative_forced_system_sector_classification": negative_forced_system_sector_classification,
    "negative_factuality_as_requirement": negative_factuality_as_requirement,
    "not_financial_target": not_financial_target,
    "applies_market_index": applies_market_index,
    "applies_equity_market": applies_equity_market,
    "applies_central_bank": applies_central_bank,
    "applies_commercial_bank": applies_commercial_bank,
    "applies_currency": applies_currency,
    "applies_equity_share": applies_equity_share,
    "applies_financial_system": applies_financial_system,
    "applies_financial_sector": applies_financial_sector,
    "applies_generic_entity": applies_generic_entity,
    "applies_generic_event": applies_generic_event,
    "applies_time_entity": applies_time_entity,
    "change_expression": change_expression,
    "accepted_market_referent": accepted_market_referent,
    "contextual_attachment": contextual_attachment,
    "source_event_mention": source_event_mention,
    "blocking_ambiguity": blocking_ambiguity,
    "sensitivity_set_marker": sensitivity_set_marker,
    "dated_descriptor_marker": dated_descriptor_marker,
    "negative_trigger_only": negative_trigger_only,
    "negative_other_code_only": negative_other_code_only,
    "negative_currency_or_value_participant_without_market": negative_currency_or_value_participant_without_market,
    "negative_automatic_promotion_of_sensitivity": negative_automatic_promotion_of_sensitivity,
    "negative_merge_distinct_triggers": negative_merge_distinct_triggers,
    "negative_collective_cross_document_identity": negative_collective_cross_document_identity,
    "distinct_triggers": distinct_triggers,
    "shared_unresolved_trigger": shared_unresolved_trigger,
    "applies_mce_currency_scope": applies_mce_currency_scope,
    "applies_mce_trigger_only": applies_mce_trigger_only,
    "applies_mce_sensitivity": applies_mce_sensitivity,
    "applies_mce_conjunction": applies_mce_conjunction,
    "applies_mce_distinct_triggers": applies_mce_distinct_triggers,
    "applies_mce_strict": applies_mce_strict,
    "direction_cue_present": direction_cue_present,
    "direction_up": direction_up,
    "direction_down": direction_down,
    "conflicting_direction_same_event": conflicting_direction_same_event,
    "applies_direction": applies_direction,
    "accepted_market_change_for_direction": accepted_market_change_for_direction,
    "event_participant_primary": event_participant_primary,
    "frame_argument_support_only": frame_argument_support_only,
    "legacy_participant_diagnostic_only": legacy_participant_diagnostic_only,
    "arg_label_alone": arg_label_alone,
    "negative_arg_label_promotes_role": negative_arg_label_promotes_role,
    "negative_invented_source_role": negative_invented_source_role,
    "missing_source_role": missing_source_role,
    "primary_participant_or_approved_equivalent": primary_participant_or_approved_equivalent,
    "accepted_market_change_event": accepted_market_change_event,
    "multiple_markets_explicit": multiple_markets_explicit,
    "multiple_events_one_market": multiple_events_one_market,
    "applies_aff_arg_only": applies_aff_arg_only,
    "applies_aff_collective": applies_aff_collective,
    "applies_aff_ambiguous": applies_aff_ambiguous,
    "applies_aff_multi_market": applies_aff_multi_market,
    "applies_aff_multi_event": applies_aff_multi_event,
    "applies_aff_missing_role": applies_aff_missing_role,
    "applies_aff_primary": applies_aff_primary,
    "applies_generic_participation": applies_generic_participation,
    "explicit_has_participant_relation": explicit_has_participant_relation,
    "negative_wrong_temporal_endpoint": negative_wrong_temporal_endpoint,
    "explicit_inference": explicit_inference,
    "active_committed_nonsuppressed": active_committed_nonsuppressed,
    "traceable_temporal_evidence": traceable_temporal_evidence,
    "explicit_event_time_relation": explicit_event_time_relation,
    "negative_event_ordering_as_event_time": negative_event_ordering_as_event_time,
    "publication_time_is_not_event_time": publication_time_is_not_event_time,
    "canonical_temporal_mapping": canonical_temporal_mapping,
    "temporal_relation_eligible": temporal_relation_eligible,
    "temporal_status_proposed": temporal_status_proposed,
    "temporal_status_suppressed": temporal_status_suppressed,
    "reasoner_entailed_inverse": reasoner_entailed_inverse,
    "inverse_generated_relation": inverse_generated_relation,
    "rule_inferred_relation": rule_inferred_relation,
    "closure_derived_relation": closure_derived_relation,
    "model_inferred_relation": model_inferred_relation,
    "negative_reasoner_entailment_as_evidence": negative_reasoner_entailment_as_evidence,
    "negative_materialise_ineligible_temporal": negative_materialise_ineligible_temporal,
    "negative_bucket_total": negative_bucket_total,
    "negative_deferred_temporal_label": negative_deferred_temporal_label,
    "applies_event_time": applies_event_time,
    "applies_temporal_bucket": applies_temporal_bucket,
    "applies_temporal_deferred": applies_temporal_deferred,
    "applies_temporal_ends": applies_temporal_ends,
    "applies_temporal_measure": applies_temporal_measure,
    "applies_temporal_reasoner": applies_temporal_reasoner,
    "applies_temporal_inverse": applies_temporal_inverse,
    "applies_temporal_suppressed": applies_temporal_suppressed,
    "applies_temporal_proposed": applies_temporal_proposed,
    "applies_temporal_rule": applies_temporal_rule,
    "applies_temporal_closure": applies_temporal_closure,
    "applies_temporal_model": applies_temporal_model,
    "applies_temporal_precedes": applies_temporal_precedes,
    "applies_temporal_follows": applies_temporal_follows,
    "applies_temporal_simultaneous": applies_temporal_simultaneous,
    "applies_temporal_during": applies_temporal_during,
    "applies_temporal_includes": applies_temporal_includes,
    "percentage_lexical_preserved": percentage_lexical_preserved,
    "value_type_numeric": value_type_numeric,
    "percentage_points_not_fraction": percentage_points_not_fraction,
    "invalid_percentage_fraction": invalid_percentage_fraction,
    "negative_percentage_as_fraction": negative_percentage_as_fraction,
    "value_lexical_present": value_lexical_present,
    "generic_number": generic_number,
    "monetary_amount_components": monetary_amount_components,
    "quantity_not_percentage": quantity_not_percentage,
    "co_presence_only_event_value": co_presence_only_event_value,
    "negative_co_presence_attachment": negative_co_presence_attachment,
    "event_value_explicitly_requested": event_value_explicitly_requested,
    "applies_percentage": applies_percentage,
    "applies_monetary": applies_monetary,
    "applies_quantity": applies_quantity,
    "applies_numerical": applies_numerical,
    "applies_event_value_link": applies_event_value_link,
    "applies_literal_value": applies_literal_value,
    "applies_evidence_record": applies_evidence_record,
    "applies_unmapped": applies_unmapped,
    "negative_unmapped_metadata": negative_unmapped_metadata,
    "negative_no_applicable_financial_rule": negative_no_applicable_financial_rule,
    "negative_no_financial_role_from_structural_participation": negative_no_financial_role_from_structural_participation,
}


def evaluate_condition(condition_id: str, view: View) -> bool:
    try:
        function = REGISTRY[condition_id]
    except KeyError as exc:
        raise ConditionError(condition_id) from exc
    return bool(function(view))


def known_condition_ids() -> list[str]:
    return sorted(REGISTRY)
