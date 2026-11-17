"""Subscription plans and limits. Limits are enforced in the services; there is no payment integration."""

from __future__ import annotations

from dataclasses import dataclass

UNLIMITED = -1


@dataclass(frozen=True)
class Plan:
    key: str
    name: str
    price_usd_month: int | None  # None = contact sales; display only
    projects: int
    members: int
    agent_tasks_month: int
    documents_per_project: int
    webhooks: int
    features: tuple[str, ...]


PLANS: dict[str, Plan] = {
    "free": Plan("free", "Free", 0, 3, 1, 100, 25, 0, ("3 projects", "Core agents", "Community support")),
    "professional": Plan("professional", "Professional", 49, 25, 3, 2000, 200, 2, ("25 projects", "All agents", "Workflows & schedules", "Webhooks")),
    "team": Plan("team", "Team", 199, 100, 15, 10000, 1000, 10, ("100 projects", "15 members", "Approval workflows", "Priority support")),
    "enterprise": Plan("enterprise", "Enterprise", None, UNLIMITED, UNLIMITED, UNLIMITED, UNLIMITED, UNLIMITED, ("Unlimited usage", "SSO (roadmap)", "Dedicated support", "Custom retention")),
}


def get_plan(key: str) -> Plan:
    return PLANS.get(key, PLANS["free"])


def within(limit: int, current: int) -> bool:
    return limit == UNLIMITED or current < limit
