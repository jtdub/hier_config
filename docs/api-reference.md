# API Reference

Auto-generated reference documentation for the `hier_config` public API.

## Start Here

The most commonly used entry points are:

- **`get_hconfig()`** — create an `HConfig` tree from raw config text and a platform
- **`WorkflowRemediation`** — compute remediation and rollback between two configs
- **`HConfig`** — the unified node class for all tree operations
- **`Platform`** — enum selecting the target network OS

For most workflows, you only need these four. The remaining classes and models are used when customizing drivers, applying tags, or building reports.

---

## Constructor Functions

::: hier_config.get_hconfig

::: hier_config.get_hconfig_driver

::: hier_config.get_hconfig_fast_load

::: hier_config.get_hconfig_from_dump

---

## Core Classes

::: hier_config.HConfig

::: hier_config.children.HConfigChildren

---

## Workflow

::: hier_config.WorkflowRemediation

---

## Reporting

::: hier_config.RemediationReporter

---

## Driver System

::: hier_config.platforms.driver_base.HConfigDriverBase

::: hier_config.platforms.driver_base.HConfigDriverRules

::: hier_config.platforms.driver_base.ParsingRules

::: hier_config.platforms.driver_base.NegationRules

::: hier_config.platforms.driver_base.IdempotencyRules

::: hier_config.platforms.driver_base.SectionalRules

---

## Models

::: hier_config.models.Platform

::: hier_config.models.MatchRule

::: hier_config.models.TagRule

::: hier_config.models.IdempotentCommandsRule

::: hier_config.models.NegationDefaultWithRule

::: hier_config.models.NegationDefaultWhenRule

::: hier_config.models.SectionalExitingRule

::: hier_config.models.SectionalOverwriteRule

::: hier_config.models.SectionalOverwriteNoNegateRule

::: hier_config.models.OrderingRule

::: hier_config.models.Dump

::: hier_config.models.DumpLine

---

## Exceptions

::: hier_config.exceptions.DuplicateChildError

`DuplicateChildError` is raised when `add_child()` encounters a child with the same text that already exists under the parent, and the parent's driver rules do not allow duplicate children. This commonly occurs when calling `merge()` with overlapping configuration sections — use `future()` instead if you need to layer configs that share the same parent paths.

---

## Utilities

::: hier_config.utils
