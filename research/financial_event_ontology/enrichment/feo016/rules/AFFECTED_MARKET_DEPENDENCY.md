# FE-AFF-001 dependency

FE-AFF-001 copies the earlier affected-market rule. No field was edited.

The rule already requires `accepted_market_change_event`. After the revised FE-MCE-001 rule rejects a source event, that required condition fails. The affected-market link is then ineligible. The relation rule does not restore the event and does not add a missing link.

Other affected-market rules that require the same accepted event are also copied unchanged. They cannot accept a link for an event the revised rule has rejected.
