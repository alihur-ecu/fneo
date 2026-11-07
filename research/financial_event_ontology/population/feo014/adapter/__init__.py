"""Corrected single-document population adapter for FEO-010A.

This copy invokes the FEO-009 enrichment engine through its public interface.
It does not copy rule logic. Corrections are limited to event-time eligibility,
participant-path classification, participation deduplication, and mention identity.
"""

__version__ = "feo010a-adapter-0.1.0"
