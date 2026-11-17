# ADR 2: Supervisor-routed LangGraph with a bounded step runner
Workers are narrow nodes over services; a pure routing function selects the next node, enabling fan-out of independent analyses and easy unit testing.
Retries/timeouts live in one runner so behaviour and persisted step events are uniform.
