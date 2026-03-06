# Migrating from v3 to v4

This guide covers the breaking changes in hier_config v4 and how to update your code.

---

## Unified HConfig Node

**v3** used three classes: `HConfigBase` (abstract), `HConfig` (root), and `HConfigChild` (non-root nodes).

**v4** uses a single `HConfig` class for both root and child positions. The `HConfigChild` and `HConfigBase` classes have been removed.

```python
# v3
from hier_config import HConfig, HConfigChild

# v4
from hier_config import HConfig  # HConfigChild no longer exists
```

Type annotations that referenced `HConfigChild` should now use `HConfig`:

```python
# v3
def process(child: HConfigChild) -> None: ...

# v4
def process(child: HConfig) -> None: ...
```

Use `node.is_root` to distinguish root from child nodes when needed.

---

## `render()` Replaces `cisco_style_text()`

The `cisco_style_text()` method has been renamed to `render()`.

```python
# v3
for line in config.all_children_sorted():
    print(line.cisco_style_text())

# v4
for line in config.all_children_sorted():
    print(line.render())
```

The `render()` method accepts the same `style` and `tag` parameters.

---

## Composable Rule Groups

**v3** stored all rules as flat fields on `HConfigDriverRules`:

```python
# v3
driver.rules.negate_with
driver.rules.idempotent_commands
driver.rules.per_line_sub
driver.rules.sectional_exiting
```

**v4** organizes rules into sub-models:

```python
# v4
driver.rules.negation.negate_with
driver.rules.negation.negation_default_when

driver.rules.idempotency.idempotent_commands
driver.rules.idempotency.idempotent_commands_avoid

driver.rules.parsing.per_line_sub
driver.rules.parsing.full_text_sub
driver.rules.parsing.indent_adjust
driver.rules.parsing.indentation
driver.rules.parsing.post_load_callbacks

driver.rules.sectional.sectional_exiting
driver.rules.sectional.sectional_overwrite
driver.rules.sectional.sectional_overwrite_no_negate

# These remain at the top level:
driver.rules.ordering
driver.rules.parent_allows_duplicate_child
driver.rules.remediation_transform_callbacks
```

### Migration mapping

| v3 path | v4 path |
|---------|---------|
| `rules.negate_with` | `rules.negation.negate_with` |
| `rules.negation_default_when` | `rules.negation.negation_default_when` |
| `rules.idempotent_commands` | `rules.idempotency.idempotent_commands` |
| `rules.idempotent_commands_avoid` | `rules.idempotency.idempotent_commands_avoid` |
| `rules.per_line_sub` | `rules.parsing.per_line_sub` |
| `rules.full_text_sub` | `rules.parsing.full_text_sub` |
| `rules.indent_adjust` | `rules.parsing.indent_adjust` |
| `rules.post_load_callbacks` | `rules.parsing.post_load_callbacks` |
| `rules.sectional_exiting` | `rules.sectional.sectional_exiting` |
| `rules.sectional_overwrite` | `rules.sectional.sectional_overwrite` |
| `rules.sectional_overwrite_no_negate` | `rules.sectional.sectional_overwrite_no_negate` |
| `rules.ordering` | `rules.ordering` *(unchanged)* |
| `rules.parent_allows_duplicate_child` | `rules.parent_allows_duplicate_child` *(unchanged)* |

---

## Frozen Rules — No More `.append()`

All rule tuples on `HConfigDriverRules` and its sub-models are **frozen Pydantic models**. You can no longer mutate them in-place:

```python
# v3 (no longer works)
driver.rules.negate_with.append(new_rule)

# v4 — use model_copy(update=...)
driver.rules = driver.rules.model_copy(update={
    "negation": driver.rules.negation.model_copy(update={
        "negate_with": (*driver.rules.negation.negate_with, new_rule),
    }),
})
```

The `driver.rules` attribute itself is a regular Python attribute on `HConfigDriverBase` and can be reassigned freely.

See [Customizing Existing Drivers](drivers.md#customizing-existing-drivers) for full examples.

---

## New Class Method Constructors

v4 adds class methods as alternative ways to create `HConfig` trees:

```python
from hier_config import HConfig, Platform

# From raw text (equivalent to get_hconfig)
config = HConfig.from_text(Platform.CISCO_IOS, config_text)

# From a serialized dump
config = HConfig.from_dump(Platform.CISCO_IOS, dump_obj)

# From pre-split lines (equivalent to get_hconfig_fast_load)
config = HConfig.from_lines(Platform.CISCO_IOS, lines)
```

These are convenience alternatives — `get_hconfig()` and the other constructor functions continue to work.

---

## New Exports

The following are now exported from `hier_config`:

- `TextStyle` — a `Literal` type for render style (`"without_comments"`, `"with_comments"`, `"merged"`)
- `ChangeDetail` — detailed information about a remediation change
- `ReportSummary` — summary statistics from `RemediationReporter`

---

## Driver Sub-Model Imports

When subclassing drivers, import the new sub-model classes:

```python
from hier_config.platforms.driver_base import (
    HConfigDriverBase,
    HConfigDriverRules,
    IdempotencyRules,
    NegationRules,
    ParsingRules,
    SectionalRules,
)
```

---

## Other Notable Changes

- **`child_count` property**: Use `node.child_count` instead of `len(node.children)` for a more readable count of direct children.
- **`all_children_sorted(key=...)`**: Accepts an optional `key` parameter for custom sort ordering.
- **`HConfigChildren.get_all()`**: Returns all children with a given text key (useful when duplicate children are allowed).
- **`negate_child()` on driver**: Negation logic moved to a three-step cascade on the driver: `negate_with` → `negation_default_when` → `swap_negation`.
- **`SectionalExitingRule.at_node_level`**: New field for controlling exit token indentation (used by IOS XR block terminators like `end-policy`).
- **`IdempotentCommandsRule.key_extract`**: New field for explicit regex-based idempotency key extraction.

---

## v2 Options Continue to Work

The `load_hconfig_v2_options()` and `load_hconfig_v2_tags()` utilities still accept v2-style dictionaries and YAML files. They now produce drivers with the new grouped rule structure automatically.
