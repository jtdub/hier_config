from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from pydantic import TypeAdapter

from hier_config import Platform, get_hconfig_driver
from hier_config.models import (
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
    TagRule,
)
from hier_config.platforms.driver_base import (
    HConfigDriverBase,
    HConfigDriverRules,
    IdempotencyRules,
    NegationRules,
    ParsingRules,
    SectionalRules,
)

HCONFIG_PLATFORM_V2_TO_V3_MAPPING = {
    "ios": Platform.CISCO_IOS,
    "iosxe": Platform.CISCO_IOS,
    "iosxr": Platform.CISCO_XR,
    "nxos": Platform.CISCO_NXOS,
    "eos": Platform.ARISTA_EOS,
    "junos": Platform.JUNIPER_JUNOS,
    "vyos": Platform.VYOS,
}


def _set_match_rule(lineage: dict[str, Any]) -> MatchRule | None:
    if startswith := lineage.get("startswith"):
        return MatchRule(startswith=startswith)
    if endswith := lineage.get("endswith"):
        return MatchRule(endswith=endswith)
    if contains := lineage.get("contains"):
        return MatchRule(contains=contains)
    if equals := lineage.get("equals"):
        return MatchRule(equals=equals)
    if re_search := lineage.get("re_search"):
        return MatchRule(re_search=re_search)

    return None


def _collect_match_rules(
    lineages: Iterable[dict[str, Any]],
) -> tuple[MatchRule, ...]:
    collected: list[MatchRule] = []
    for lineage in lineages:
        match_rule = _set_match_rule(lineage)
        if match_rule is not None:
            collected.append(match_rule)
    return tuple(collected)


def read_text_from_file(file_path: str) -> str:
    """Function that loads the contents of a file into memory.

    Args:
        file_path (str): The path to the configuration file.

    Returns:
        str: The configuration file contents as a string.

    """
    return Path(file_path).read_text(encoding="utf-8")


def load_hier_config_tags(tags_file: str) -> tuple[TagRule, ...]:
    """Loads and validates Hier Config tags from a YAML file.

    Args:
        tags_file (str): Path to the YAML file containing the tags.

    Returns:
        Tuple[TagRule, ...]: A tuple of validated TagRule objects.

    """
    tags_data = yaml.safe_load(read_text_from_file(file_path=tags_file))
    return TypeAdapter(tuple[TagRule, ...]).validate_python(tags_data)


def hconfig_v2_os_v3_platform_mapper(os_name: str) -> Platform:
    """Map a Hier Config v2 operating system name to a v3 Platform enumeration.

    Args:
        os_name (str): The name of the OS as defined in Hier Config v2.

    Returns:
        Platform: The corresponding Platform enumeration for Hier Config v3.

    Example:
        >>> hconfig_v2_os_v3_platform_mapper("CISCO_IOS")
        <Platform.CISCO_IOS: 'ios'>

    """
    return HCONFIG_PLATFORM_V2_TO_V3_MAPPING.get(os_name, Platform.GENERIC)


def hconfig_v3_platform_v2_os_mapper(platform: Platform) -> str:
    """Map a Hier Config v3 Platform enumeration to a v2 operating system name.

    Args:
        platform (Platform): A Platform enumeration from Hier Config v3.

    Returns:
        str: The corresponding OS name for Hier Config v2.

    Example:
        >>> hconfig_v3_platform_v2_os_mapper(Platform.CISCO_IOS)
        "ios"

    """
    for os_name, plat in HCONFIG_PLATFORM_V2_TO_V3_MAPPING.items():
        if plat == platform:
            return os_name

    return "generic"


def _process_simple_rules(
    options: dict[str, Any],
    key: str,
    rule_class: type[Any],
) -> tuple[Any, ...]:
    """Process rules that only need match_rules."""
    result: list[Any] = []
    for rule in options.get(key, ()):
        match_rules = _collect_match_rules(rule.get("lineage", []))
        result.append(rule_class(match_rules=match_rules))
    return tuple(result)


def _process_custom_rules(
    options: dict[str, Any],
) -> dict[str, tuple[Any, ...]]:
    """Process rules that require custom handling. Returns a dict of rule tuples."""
    result: dict[str, tuple[Any, ...]] = {}

    ordering = tuple(
        OrderingRule(
            match_rules=_collect_match_rules(rule.get("lineage", [])),
            weight=rule.get("order", 500) - 500,
        )
        for rule in options.get("ordering", ())
    )
    if ordering:
        result["ordering"] = ordering

    indent_adjust = tuple(
        IndentAdjustRule(
            start_expression=rule.get("start_expression"),
            end_expression=rule.get("end_expression"),
        )
        for rule in options.get("indent_adjust", ())
    )
    if indent_adjust:
        result["indent_adjust"] = indent_adjust

    sectional_exiting = tuple(
        SectionalExitingRule(
            match_rules=_collect_match_rules(rule.get("lineage", [])),
            exit_text=rule.get("exit_text", ""),
        )
        for rule in options.get("sectional_exiting", ())
    )
    if sectional_exiting:
        result["sectional_exiting"] = sectional_exiting

    full_text_sub = tuple(
        FullTextSubRule(search=rule.get("search", ""), replace=rule.get("replace", ""))
        for rule in options.get("full_text_sub", ())
    )
    if full_text_sub:
        result["full_text_sub"] = full_text_sub

    per_line_sub = tuple(
        PerLineSubRule(search=rule.get("search", ""), replace=rule.get("replace", ""))
        for rule in options.get("per_line_sub", ())
    )
    if per_line_sub:
        result["per_line_sub"] = per_line_sub

    negate_with = tuple(
        NegationDefaultWithRule(
            match_rules=_collect_match_rules(rule.get("lineage", [])),
            use=rule.get("use", ""),
        )
        for rule in options.get("negation_negate_with", ())
    )
    if negate_with:
        result["negate_with"] = negate_with

    return result


def load_hconfig_v2_options(
    v2_options: dict[str, Any] | str, platform: Platform
) -> HConfigDriverBase:
    """Load Hier Config v2 options to v3 driver format from either a dictionary or a file.

    Args:
        v2_options (Union[dict, str]): Either a dictionary containing v2 options or
            a file path to a YAML file containing the v2 options.
        platform (Platform): The Hier Config v3 Platform enum for the target platform.

    Returns:
        HConfigDriverBase: A v3 driver instance with the migrated rules.

    """
    if isinstance(v2_options, str):
        v2_options = yaml.safe_load(read_text_from_file(file_path=v2_options))

    if not isinstance(v2_options, dict):
        msg = "v2_options must be a dictionary or a valid file path."
        raise TypeError(msg)

    return load_driver_options(v2_options, platform)


def load_driver_options(
    options: dict[str, Any] | str, platform_or_driver: Platform | HConfigDriverBase
) -> HConfigDriverBase:
    """Load driver options from a dictionary or YAML file and merge them
    into a platform driver.

    This is the generic version of load_hconfig_v2_options that works with
    any options dictionary format. It creates a driver for the given platform,
    then extends its rules with the provided options.

    Args:
        options: Either a dictionary containing options or a file path
            to a YAML file containing the options.
        platform_or_driver: The Platform enum or an existing driver instance.

    Returns:
        HConfigDriverBase: A driver instance with the merged rules.

    """
    if isinstance(options, str):
        options = yaml.safe_load(read_text_from_file(file_path=options))

    if not isinstance(options, dict):
        msg = "options must be a dictionary or a valid file path."
        raise TypeError(msg)

    driver = (
        get_hconfig_driver(platform_or_driver)
        if isinstance(platform_or_driver, Platform)
        else platform_or_driver
    )

    # Collect simple rules
    simple_rules_config: dict[str, tuple[Any, ...]] = {}

    simple_mapping: tuple[tuple[str, type[Any]], ...] = (
        ("sectional_overwrite", SectionalOverwriteRule),
        ("sectional_overwrite_no_negate", SectionalOverwriteNoNegateRule),
        ("parent_allows_duplicate_child", ParentAllowsDuplicateChildRule),
        ("idempotent_commands_blacklist", IdempotentCommandsAvoidRule),
        ("idempotent_commands_avoid", IdempotentCommandsAvoidRule),
        ("idempotent_commands", IdempotentCommandsRule),
        ("negation_default_when", NegationDefaultWhenRule),
    )

    for key, rule_class in simple_mapping:
        new_rules = _process_simple_rules(options, key, rule_class)
        if new_rules:
            # Map blacklist key to the correct field name
            field_name = (
                "idempotent_commands_avoid"
                if key == "idempotent_commands_blacklist"
                else key
            )
            simple_rules_config[field_name] = new_rules

    # Collect custom rules
    custom_rules = _process_custom_rules(options)

    # Merge all new rules with existing driver rules
    all_new_rules = {**simple_rules_config, **custom_rules}

    if all_new_rules:
        driver.rules = _merge_rules(driver.rules, all_new_rules)

    return driver


_FIELD_TO_GROUP: dict[str, str | None] = {
    # SectionalRules
    "sectional_exiting": "sectional",
    "sectional_overwrite": "sectional",
    "sectional_overwrite_no_negate": "sectional",
    # ParsingRules
    "full_text_sub": "parsing",
    "per_line_sub": "parsing",
    "indent_adjust": "parsing",
    # NegationRules
    "negate_with": "negation",
    "negation_default_when": "negation",
    # IdempotencyRules
    "idempotent_commands": "idempotency",
    "idempotent_commands_avoid": "idempotency",
    # Flat on HConfigDriverRules
    "ordering": None,
    "parent_allows_duplicate_child": None,
}

_GROUP_CLASSES: dict[str, type[Any]] = {
    "sectional": SectionalRules,
    "parsing": ParsingRules,
    "negation": NegationRules,
    "idempotency": IdempotencyRules,
}


def _merge_rules(
    existing: HConfigDriverRules, new_rules: dict[str, tuple[Any, ...]]
) -> HConfigDriverRules:
    """Merge new rule tuples into an existing HConfigDriverRules, respecting grouped structure."""
    # Collect updates grouped by sub-model
    group_updates: dict[str, dict[str, tuple[Any, ...]]] = {}
    flat_updates: dict[str, tuple[Any, ...]] = {}

    for field_name, rules in new_rules.items():
        group = _FIELD_TO_GROUP.get(field_name)
        if group is None:
            existing_val = getattr(existing, field_name, ())
            flat_updates[field_name] = (*existing_val, *rules)
        else:
            group_updates.setdefault(group, {})[field_name] = rules

    # Build updated sub-models
    sub_model_updates: dict[str, Any] = {}
    for group_name, fields in group_updates.items():
        sub_model = getattr(existing, group_name)
        merged: dict[str, Any] = {}
        for field_name, new_vals in fields.items():
            existing_val = getattr(sub_model, field_name, ())
            merged[field_name] = (*existing_val, *new_vals)
        group_cls = _GROUP_CLASSES[group_name]
        # Preserve existing fields not being updated.
        # model_dump() cannot serialize callable fields (e.g. post_load_callbacks),
        # so we restore them from the original sub-model when present.
        existing_data = {
            k: v for k, v in sub_model.model_dump().items() if k not in merged
        }
        if group_name == "parsing" and "post_load_callbacks" not in merged:
            existing_data["post_load_callbacks"] = sub_model.post_load_callbacks
        sub_model_updates[group_name] = group_cls(**existing_data, **merged)

    # Build final HConfigDriverRules
    result_kwargs: dict[str, Any] = {
        "parsing": sub_model_updates.get("parsing", existing.parsing),
        "negation": sub_model_updates.get("negation", existing.negation),
        "idempotency": sub_model_updates.get("idempotency", existing.idempotency),
        "sectional": sub_model_updates.get("sectional", existing.sectional),
        "ordering": flat_updates.get("ordering", existing.ordering),
        "parent_allows_duplicate_child": flat_updates.get(
            "parent_allows_duplicate_child", existing.parent_allows_duplicate_child
        ),
        "remediation_transform_callbacks": existing.remediation_transform_callbacks,
    }

    return HConfigDriverRules(**result_kwargs)


def load_hconfig_v2_options_from_file(
    options_file: str, platform: Platform
) -> HConfigDriverBase:
    """Load Hier Config v2 options file to v3 driver format.

    Args:
        options_file (str): The v2 options file.
        platform (Platform): The Hier Config v3 Platform enum for the target platform.

    Returns:
        HConfigDriverBase: A v3 driver instance with the migrated rules.

    """
    hconfig_options = yaml.safe_load(read_text_from_file(file_path=options_file))
    return load_hconfig_v2_options(v2_options=hconfig_options, platform=platform)


def load_hconfig_v2_tags(
    v2_tags: list[dict[str, Any]] | str,
) -> tuple["TagRule"] | tuple["TagRule", ...]:
    """Convert v2-style tags into v3-style TagRule Pydantic objects for Hier Config.

    Args:
        v2_tags (Union[list[dict[str, Any]], str]):
            Either a list of dictionaries representing v2-style tags or a file path
            to a YAML file containing the v2-style tags.
            - If a list is provided, each dictionary should contain:
              - `lineage`: A list of dictionaries with rules (e.g., `startswith`, `endswith`).
              - `add_tags`: A string representing the tag to add.
            - If a file path is provided, it will be read and parsed as YAML.

    Returns:
        Tuple[TagRule]: A tuple of TagRule Pydantic objects representing v3-style tags.

    """
    # Load tags from a file if a string is provided
    if isinstance(v2_tags, str):
        v2_tags = yaml.safe_load(read_text_from_file(file_path=v2_tags))

    # Ensure v2_tags is a list
    if not isinstance(v2_tags, list):
        msg = "v2_tags must be a list of dictionaries or a valid file path."
        raise TypeError(msg)

    v3_tags: list[TagRule] = []

    for v2_tag in v2_tags:
        if "lineage" in v2_tag and "add_tags" in v2_tag:
            # Extract the v2 fields
            lineage_rules = v2_tag["lineage"]
            tags = v2_tag["add_tags"]

            # Convert to MatchRule objects
            match_rules = tuple(
                match_rule
                for lineage in lineage_rules
                if (match_rule := _set_match_rule(lineage)) is not None
            )

            # Create the TagRule object
            v3_tag = TagRule(match_rules=match_rules, apply_tags=frozenset([tags]))
            v3_tags.append(v3_tag)

    return tuple(v3_tags)
