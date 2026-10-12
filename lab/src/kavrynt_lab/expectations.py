"""The governance the lab expects Kavrynt to enforce (policies/expectations.yaml)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

Decision = Literal["allow", "deny", "approve"]
DECISIONS: tuple[Decision, ...] = ("allow", "deny", "approve")
TOP_LEVEL_KEYS = {"default", "rules"}
RULE_KEYS = {"agent", "server", "tool", "decision"}


@dataclass(frozen=True)
class Rule:
    agent: str
    server: str
    tool: str
    decision: Decision

    def matches(self, agent: str, server: str, tool: str) -> bool:
        return all(
            p in ("*", value)
            for p, value in ((self.agent, agent), (self.server, server), (self.tool, tool))
        )


@dataclass(frozen=True)
class Expectations:
    rules: tuple[Rule, ...]
    default: Decision = "deny"

    def decide(self, agent: str, server: str, tool: str) -> Decision:
        for rule in self.rules:
            if rule.matches(agent, server, tool):
                return rule.decision
        return self.default

    @classmethod
    def load(cls, path: str | Path) -> Expectations:
        """Strict: a typo must fail loudly, never widen a rule. Every rule names agent, server
        and tool explicitly ("*" for any) and a decision; unknown keys are errors."""
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict) or set(raw) - TOP_LEVEL_KEYS:
            raise ValueError(f"expectations: only {sorted(TOP_LEVEL_KEYS)} are allowed")
        default = raw.get("default", "deny")
        if default not in DECISIONS:
            raise ValueError(f"default must be one of {DECISIONS}")
        rules = []
        for i, item in enumerate(raw.get("rules") or []):
            if not isinstance(item, dict) or set(item) != RULE_KEYS:
                keys = sorted(item) if isinstance(item, dict) else item
                raise ValueError(f"rule {i}: needs exactly {sorted(RULE_KEYS)}, got {keys}")
            for key in ("agent", "server", "tool"):
                if not isinstance(item[key], str) or not item[key].strip():
                    raise ValueError(f'rule {i}: {key} must be a name or "*"')
            if item["decision"] not in DECISIONS:
                raise ValueError(f"rule {i}: decision must be one of {DECISIONS}")
            rules.append(Rule(item["agent"], item["server"], item["tool"], item["decision"]))
        return cls(rules=tuple(rules), default=default)
