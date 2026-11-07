"""Population profiles stay separate. Accepted outputs are not copied across them."""

from __future__ import annotations

from engine.constants import PROFILES


def empty_buckets() -> dict[str, list]:
    return {profile: [] for profile in PROFILES}


def bucket_decision(buckets: dict[str, list], decision: dict) -> None:
    profile = decision.get("profile")
    if profile not in buckets:
        raise ValueError(f"Unknown population profile: {profile}")
    buckets[profile].append(decision)


def accepted_in(buckets: dict[str, list], profile: str) -> list[dict]:
    return [item for item in buckets.get(profile, []) if item.get("status") == "accepted"]
