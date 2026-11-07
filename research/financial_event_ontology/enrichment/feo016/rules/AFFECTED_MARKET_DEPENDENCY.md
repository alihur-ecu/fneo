# FE-AFF-001 dependency

FE-AFF-001 is a byte copy of the FEO-009 rule. No field was edited.

The rule already requires `accepted_market_change_event`. After FE-MCE-001 version feo016-0.1.0 rejects a source event, that required condition fails. The affected-market link is then ineligible. The relation rule does not restore the event and does not add a missing link.

Other affected-market rules that require the same accepted event are also copied unchanged. They cannot accept a link for an event the revised rule has rejected.
