from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from re import Match, search

from pydantic import PositiveInt

from hier_config.models import (
    BaseModel,
    FullTextSubRule,
    IdempotentCommandsAvoidRule,
    IdempotentCommandsRule,
    IndentAdjustRule,
    MatchRule,
    NegationDefaultWhenRule,
    NegationDefaultWithRule,
    OrderingRule,
    ParentAllowsDuplicateChildRule,
    PerLineSubRule,
    SectionalExitingRule,
    SectionalOverwriteNoNegateRule,
    SectionalOverwriteRule,
)
from hier_config.root import HConfig


class ParsingRules(BaseModel):
    """Rules governing config text parsing and post-load normalisation."""

    full_text_sub: tuple[FullTextSubRule, ...] = ()
    per_line_sub: tuple[PerLineSubRule, ...] = ()
    indent_adjust: tuple[IndentAdjustRule, ...] = ()
    indentation: PositiveInt = 2
    post_load_callbacks: tuple[Callable[..., None], ...] = ()


class NegationRules(BaseModel):
    """Rules controlling how commands are negated during remediation."""

    negate_with: tuple[NegationDefaultWithRule, ...] = ()
    negation_default_when: tuple[NegationDefaultWhenRule, ...] = ()


class IdempotencyRules(BaseModel):
    """Rules declaring idempotent command families (last value wins)."""

    idempotent_commands: tuple[IdempotentCommandsRule, ...] = ()
    idempotent_commands_avoid: tuple[IdempotentCommandsAvoidRule, ...] = ()


class SectionalRules(BaseModel):
    """Rules for hierarchical section exit commands and overwrite semantics."""

    sectional_exiting: tuple[SectionalExitingRule, ...] = ()
    sectional_overwrite: tuple[SectionalOverwriteRule, ...] = ()
    sectional_overwrite_no_negate: tuple[SectionalOverwriteNoNegateRule, ...] = ()


class HConfigDriverRules(BaseModel):
    """Pydantic model holding all rule collections for a platform driver.

    Rules are grouped by category into sub-models for clarity.  Fields that
    don't naturally group (ordering, duplicate-child, remediation callbacks)
    remain at the top level.
    """

    parsing: ParsingRules = ParsingRules()
    negation: NegationRules = NegationRules()
    idempotency: IdempotencyRules = IdempotencyRules()
    sectional: SectionalRules = SectionalRules()
    ordering: tuple[OrderingRule, ...] = ()
    parent_allows_duplicate_child: tuple[ParentAllowsDuplicateChildRule, ...] = ()
    remediation_transform_callbacks: tuple[Callable[..., None], ...] = ()


class HConfigDriverBase(ABC):
    """Defines all hier_config options, rules, and rule checking methods.
    Override methods as needed.
    """

    def __init__(self) -> None:
        self.rules = self._instantiate_rules()

    def idempotent_for(
        self,
        config: HConfig,
        other_children: Iterable[HConfig],
    ) -> HConfig | None:
        for rule in self.rules.idempotency.idempotent_commands:
            if not config.is_lineage_match(rule.match_rules):
                continue

            config_key = self._idempotency_key(
                config, rule.match_rules, rule.key_extract
            )

            for other_child in other_children:
                if not other_child.is_lineage_match(rule.match_rules):
                    continue

                if (
                    self._idempotency_key(
                        other_child, rule.match_rules, rule.key_extract
                    )
                    == config_key
                ):
                    return other_child

        return None

    def negate_child(self, child: HConfig) -> HConfig:
        """Negate a child using the three-step driver cascade.

        1. Check ``negate_with`` rules for a fixed replacement command.
        2. Check ``negation_default_when`` rules for the ``default`` form.
        3. Fall back to ``swap_negation`` (toggle the negation prefix).
        """
        if negate_with := self.negate_with(child):
            child.text = negate_with
            return child
        if self._use_default_for_negation(child):
            child.text = f"default {child.text_without_negation}"
            return child
        return self.swap_negation(child)

    def negate_with(self, config: HConfig) -> str | None:
        for with_rule in self.rules.negation.negate_with:
            if config.is_lineage_match(with_rule.match_rules):
                return with_rule.use
        return None

    def swap_negation(self, child: HConfig) -> HConfig:
        """Swap negation of a `child.text`."""
        if child.text.startswith(self.negation_prefix):
            child.text = child.text_without_negation
        else:
            child.text = f"{self.negation_prefix}{child.text}"

        return child

    def _use_default_for_negation(self, config: HConfig) -> bool:
        return any(
            config.is_lineage_match(rule.match_rules)
            for rule in self.rules.negation.negation_default_when
        )

    def _idempotency_key(
        self,
        config: HConfig,
        match_rules: tuple[MatchRule, ...],
        key_extract: str | None = None,
    ) -> tuple[str, ...]:
        """Build a structural identity for `config` that respects driver rules.

        Args:
            config: The child being evaluated for idempotency.
            match_rules: The match rules describing the lineage signature.
            key_extract: Optional regex with a named group ``key`` applied to
                the leaf (last) lineage component.  When provided, it overrides
                the heuristic key generation for that component.

        Returns:
            A tuple of string fragments representing the idempotency key.

        """
        lineage = tuple(config.lineage())
        if len(lineage) != len(match_rules):
            return ()

        components: list[str] = []
        last_index = len(lineage) - 1
        for index, (child, rule) in enumerate(zip(lineage, match_rules, strict=False)):
            # Apply key_extract only to the leaf component
            if key_extract is not None and index == last_index:
                extracted = self._key_from_extract(child.text, key_extract)
                if extracted is not None:
                    components.append(extracted)
                    continue
            components.append(self._idempotency_component_key(child, rule))
        return tuple(components)

    def _idempotency_component_key(
        self,
        child: HConfig,
        rule: MatchRule,
    ) -> str:
        """Derive the structural key for a single lineage component.

        Args:
            child: The lineage child contributing to the key.
            rule: The rule governing how to match the child.

        Returns:
            A string fragment representing the component key.

        """
        text = child.text
        normalized_text = text.removeprefix(self.negation_prefix)

        parts: list[str] = []
        parts.extend(self._key_from_equals(rule.equals, text))
        parts.extend(self._key_from_prefix(rule.startswith, normalized_text))
        parts.extend(self._key_from_suffix(rule.endswith, normalized_text))
        parts.extend(self._key_from_contains(rule.contains, normalized_text))
        parts.extend(self._key_from_regex(rule.re_search, normalized_text, text))

        if not parts:
            parts.append(f"text|{normalized_text}")

        return ";".join(parts)

    @staticmethod
    def _key_from_equals(equals: str | frozenset[str] | None, text: str) -> list[str]:
        """Return key fragments constrained by `equals` match rules.

        Args:
            equals: The equals constraint specified by the rule.
            text: The original command text to fall back on for sets.

        Returns:
            A list containing zero or one key fragments.

        """
        if equals is None:
            return []
        if isinstance(equals, str):
            return [f"equals|{equals}"]
        return [f"equals|{text}"]

    def _key_from_prefix(
        self,
        prefix: str | tuple[str, ...] | None,
        normalized_text: str,
    ) -> list[str]:
        """Return key fragments for `startswith` match rules.

        Args:
            prefix: The `startswith` constraint(s) to evaluate.
            normalized_text: The command text without the negation prefix.

        Returns:
            A list containing zero or one key fragments.

        """
        if prefix is None:
            return []
        matched = self._match_prefix(normalized_text, prefix)
        if matched is None:
            return []
        return [f"startswith|{matched}"]

    def _key_from_suffix(
        self,
        suffix: str | tuple[str, ...] | None,
        normalized_text: str,
    ) -> list[str]:
        """Return key fragments for `endswith` match rules.

        Args:
            suffix: The `endswith` constraint(s) to evaluate.
            normalized_text: The command text without the negation prefix.

        Returns:
            A list containing zero or one key fragments.

        """
        if suffix is None:
            return []
        matched = self._match_suffix(normalized_text, suffix)
        if matched is None:
            return []
        return [f"endswith|{matched}"]

    def _key_from_contains(
        self,
        contains: str | tuple[str, ...] | None,
        normalized_text: str,
    ) -> list[str]:
        """Return key fragments for `contains` match rules.

        Args:
            contains: The `contains` constraint(s) to evaluate.
            normalized_text: The command text without the negation prefix.

        Returns:
            A list containing zero or one key fragments.

        """
        if contains is None:
            return []
        matched = self._match_contains(normalized_text, contains)
        if matched is None:
            return []
        return [f"contains|{matched}"]

    def _key_from_regex(
        self,
        pattern: str | None,
        normalized_text: str,
        original_text: str,
    ) -> list[str]:
        """Return key fragments derived from regex match rules.

        Args:
            pattern: The regex pattern to match.
            normalized_text: The command text without the negation prefix.
            original_text: The command text including any negation.

        Returns:
            A list containing zero or one key fragments.

        """
        if pattern is None:
            return []

        match = search(pattern, normalized_text)
        match_source = normalized_text
        if match is None:
            match = search(pattern, original_text)
            match_source = original_text

        if match is None:
            return []

        regex_key = self._normalize_regex_key(pattern, match_source, match)
        return [f"re|{regex_key}"]

    @staticmethod
    def _key_from_extract(text: str, key_extract: str) -> str | None:
        """Apply an explicit ``key_extract`` regex to derive the idempotency key.

        The regex must contain a named group ``key``.  If the pattern matches
        and the group is non-empty, the extracted value is returned as the
        component key.

        Args:
            text: The command text to match against.
            key_extract: Regex pattern with a ``(?P<key>...)`` named group.

        Returns:
            A key string like ``"extract|<value>"`` on success, or ``None``
            when the pattern does not match or the group is empty.

        """
        match = search(key_extract, text)
        if match is None:
            return None
        try:
            key_value = match.group("key")
        except IndexError:
            return None
        if key_value:
            return f"extract|{key_value}"
        return None

    @staticmethod
    def _match_prefix(value: str, prefix: str | tuple[str, ...]) -> str | None:
        if isinstance(prefix, tuple):
            matches = [candidate for candidate in prefix if value.startswith(candidate)]
            if matches:
                return max(matches, key=len)
            return None

        if value.startswith(prefix):
            return prefix

        return None

    @staticmethod
    def _match_suffix(value: str, suffix: str | tuple[str, ...]) -> str | None:
        if isinstance(suffix, tuple):
            matches = [candidate for candidate in suffix if value.endswith(candidate)]
            if matches:
                return max(matches, key=len)
            return None

        if value.endswith(suffix):
            return suffix

        return None

    @staticmethod
    def _match_contains(value: str, contains: str | tuple[str, ...]) -> str | None:
        if isinstance(contains, tuple):
            matches = [candidate for candidate in contains if candidate in value]
            if matches:
                return max(matches, key=len)
            return None

        if contains in value:
            return contains

        return None

    @staticmethod
    def _normalize_regex_key(pattern: str, value: str, match: Match[str]) -> str:
        """Normalize regex matches so equivalent commands hash the same."""
        result = match.group(0)

        if match.re.groups:
            groups = tuple(g or "" for g in match.groups())
            if any(groups):
                normalized_groups = tuple(group.strip() for group in groups)
                if any(normalized_groups):
                    return "|".join(normalized_groups)

        trimmed_pattern = pattern.rstrip("$")
        for suffix in (".*", ".+"):
            if trimmed_pattern.endswith(suffix):
                candidate_pattern = trimmed_pattern[: -len(suffix)]
                if not candidate_pattern:
                    break
                trimmed_match = search(candidate_pattern, value)
                if trimmed_match is not None:
                    candidate = trimmed_match.group(0).strip()
                    if candidate:
                        return candidate
                break

        return result.strip()

    @property
    def declaration_prefix(self) -> str:
        return ""

    @property
    def negation_prefix(self) -> str:
        return "no "

    @staticmethod
    def config_preprocessor(config_text: str) -> str:
        return config_text

    @staticmethod
    @abstractmethod
    def _instantiate_rules() -> HConfigDriverRules:
        pass
