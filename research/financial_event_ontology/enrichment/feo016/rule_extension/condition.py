"""Structural negative condition for FE-MCE-001, version feo016-0.1.0.

The predicate is not in the closed FEO-009 condition vocabulary. The FEO-016
runner registers it before loading rules. The FEO-009 engine source is not
modified, and this module is not imported by that engine.
"""

from __future__ import annotations


def trigger_forms(view) -> list[str]:
    """Trigger form, lemma, and candidate label. Sentence evidence is excluded."""
    raw = [
        view.c.get("trigger_or_lexical_form"),
        view.c.get("lemma"),
        (view.f or {}).get("label"),
    ]
    forms: list[str] = []
    for value in raw:
        text = " ".join(str(value or "").split())
        if text and text not in forms:
            forms.append(text)
    return forms


def trigger_is_change_expression(view) -> bool:
    """True when the trigger form or lemma is in the closed change vocabulary."""
    return any(view.lex.change_expression(form) for form in trigger_forms(view))


def negative_market_not_undergoer_of_trigger(view) -> bool:
    """The attached market is not the entity undergoing the change of this trigger.

    Fires only when an accepted market or index is contextually attached and a
    change expression is available, but that change expression is not the
    trigger. A match confined to the sentence evidence is co-presence. An
    explicit change flag on a trigger that is not itself a change expression
    is the same structural failure.

    Argument labels, document identifiers, sentence strings, and market names
    are not consulted.
    """
    from engine.conditions import accepted_market_referent, contextual_attachment

    if view.kind != "event_candidate":
        return False
    if trigger_is_change_expression(view):
        return False
    if not contextual_attachment(view) or not accepted_market_referent(view):
        return False
    if view.flag("change_expression") is True:
        return True
    return bool(view.lex.change_expression(view.evidence()))
