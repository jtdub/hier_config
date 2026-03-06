from __future__ import annotations

from itertools import chain
from logging import getLogger
from re import search
from typing import TYPE_CHECKING, Any

from .children import HConfigChildren
from .exceptions import DuplicateChildError
from .models import Dump, DumpLine, Instance, MatchRule, SetLikeOfStr, TextStyle

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

    from .models import Platform
    from .platforms.driver_base import HConfigDriverBase

logger = getLogger(__name__)


class HConfig:  # noqa: PLR0904  pylint: disable=too-many-instance-attributes
    """Unified node for hierarchical configuration trees.

    When ``driver_or_parent`` is an :class:`HConfigDriverBase`, the node is the
    **root** of a new tree.  When it is another :class:`HConfig` instance, the
    node becomes a **child** of that parent.
    """

    __slots__ = (
        "_driver",
        "_parent",
        "_tags",
        "_text",
        "children",
        "comments",
        "facts",
        "instances",
        "new_in_config",
        "order_weight",
        "real_indent_level",
    )

    def __init__(
        self,
        driver_or_parent: HConfigDriverBase | HConfig | None = None,
        text: str = "",
        *,
        driver: HConfigDriverBase | None = None,
    ) -> None:
        # Support `HConfig(driver=drv)` keyword form for backward compat
        if driver is not None and driver_or_parent is None:
            driver_or_parent = driver
        if driver_or_parent is None:
            message = "driver_or_parent is required"
            raise TypeError(message)

        self.children = HConfigChildren()

        if isinstance(driver_or_parent, HConfig):
            # Child node
            self._driver: HConfigDriverBase | None = None
            self._parent: HConfig | None = driver_or_parent
            self._text = text.strip()
        else:
            # Root node
            self._driver = driver_or_parent
            self._parent = None
            self._text = ""

        self.real_indent_level: int = -1

        self.order_weight: int = 0
        self._tags: set[str] = set()
        self.comments: set[str] = set()
        self.new_in_config: bool = False
        self.instances: list[Instance] = []
        self.facts: dict[Any, Any] = {}

    # ------------------------------------------------------------------
    # Class method constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_text(
        cls,
        platform_or_driver: Platform | HConfigDriverBase,
        config_raw: str = "",
    ) -> HConfig:
        """Create an HConfig tree from raw configuration text."""
        from .constructors import get_hconfig  # noqa: PLC0415

        return get_hconfig(platform_or_driver, config_raw)

    @classmethod
    def from_dump(
        cls,
        platform_or_driver: Platform | HConfigDriverBase,
        dump: Dump,
    ) -> HConfig:
        """Create an HConfig tree from a serialised dump."""
        from .constructors import get_hconfig_from_dump  # noqa: PLC0415

        return get_hconfig_from_dump(platform_or_driver, dump)

    @classmethod
    def from_lines(
        cls,
        platform_or_driver: Platform | HConfigDriverBase,
        lines: list[str] | tuple[str, ...] | str,
    ) -> HConfig:
        """Create an HConfig tree from pre-split lines."""
        from .constructors import get_hconfig_fast_load  # noqa: PLC0415

        return get_hconfig_fast_load(platform_or_driver, lines)

    # ------------------------------------------------------------------
    # Dunder methods
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        if self.is_root:
            return "\n".join(str(c) for c in sorted(self.children))
        return "\n".join(self.lines(sectional_exiting=True))

    def __repr__(self) -> str:
        if self.is_root:
            return f"HConfig(driver={self.driver.__class__.__name__}, lines={self.dump_simple()})"
        return f"HConfig(parent={self._parent!r}, text={self.text!r})"

    def __lt__(self, other: HConfig) -> bool:
        return self.order_weight < other.order_weight

    def __hash__(self) -> int:
        if self.is_root:
            return hash(tuple(self.children))
        return hash((self.text, *self.children))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, HConfig):
            return NotImplemented
        if self.is_root != other.is_root:
            return NotImplemented
        if not self.is_root and self.text != other.text:
            return False
        return self.children == other.children

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __len__(self) -> int:
        return sum(1 for _ in self.all_children())

    def __bool__(self) -> bool:
        return True

    def __iter__(self) -> Iterator[HConfig]:
        return iter(self.children)

    # ------------------------------------------------------------------
    # Core properties
    # ------------------------------------------------------------------

    @property
    def is_root(self) -> bool:
        """True if this node is the root of the configuration tree."""
        return self._parent is None

    @property
    def parent(self) -> HConfig | None:
        """The parent node, or ``None`` for the root."""
        return self._parent

    @property
    def root(self) -> HConfig:
        """The root :class:`HConfig` at the base of the tree."""
        if self._parent is None:
            return self
        return self._parent.root

    @property
    def driver(self) -> HConfigDriverBase:
        """The platform driver for this tree."""
        if self._driver is not None:
            return self._driver
        return self.root.driver

    @property
    def text(self) -> str:
        return self._text

    @text.setter
    def text(self, value: str) -> None:
        self._text = value.strip()
        if self._parent is not None:
            self._parent.children.rebuild_mapping()

    @property
    def text_without_negation(self) -> str:
        return self.text.removeprefix(self.driver.negation_prefix)

    # ------------------------------------------------------------------
    # Tree structure
    # ------------------------------------------------------------------

    @property
    def is_leaf(self) -> bool:
        """True if this is a non-root node with no children."""
        if self.is_root:
            return False
        return not bool(self.children)

    @property
    def is_branch(self) -> bool:
        """True if this is the root or a non-root node with children."""
        if self.is_root:
            return True
        return bool(self.children)

    @property
    def child_count(self) -> int:
        """Return the number of direct children."""
        return len(self.children)

    def depth(self) -> int:
        """Distance to the root (0 for root, 1 for top-level children, etc.)."""
        if self._parent is None:
            return 0
        return self._parent.depth() + 1

    def lineage(self) -> Iterator[HConfig]:
        """Yield parent lineage from root down to self, excluding the root."""
        if self._parent is not None:
            yield from self._parent.lineage()
            yield self

    def path(self) -> Iterator[str]:
        """Yield the text of each node in the lineage."""
        for node in self.lineage():
            yield node.text

    @property
    def indentation(self) -> str:
        return " " * self.driver.rules.parsing.indentation * (self.depth() - 1)

    # ------------------------------------------------------------------
    # Children management
    # ------------------------------------------------------------------

    def add_children(self, lines: Iterable[str]) -> None:
        """Add child instances."""
        for line in lines:
            self.add_child(line)

    def add_child(
        self,
        text: str,
        *,
        return_if_present: bool = False,
        check_if_present: bool = True,
    ) -> HConfig:
        """Add a child node."""
        if not text:
            message = "text was empty"
            raise ValueError(message)

        if check_if_present and (child := self.children.get(text)):
            if self._is_duplicate_child_allowed():
                new_child = self.instantiate_child(text)
                self.children.append(new_child)
                return new_child
            if return_if_present:
                return child
            message = f"Found a duplicate section: {(*self.path(), text)}"
            raise DuplicateChildError(message)

        new_child = self.instantiate_child(text)
        self.children.append(new_child)
        return new_child

    def add_children_deep(self, lines: Iterable[str]) -> HConfig:
        """Add child instances deeply, creating the hierarchy as needed."""
        base: HConfig = self
        for line in lines:
            base = base.add_child(line, return_if_present=True)
        return base

    def add_deep_copy_of(
        self,
        child_to_add: HConfig,
        *,
        merged: bool = False,
    ) -> HConfig:
        """Add a nested copy of a child to self."""
        new_child = self.add_shallow_copy_of(child_to_add, merged=merged)
        for child in child_to_add.children:
            new_child.add_deep_copy_of(child, merged=merged)
        return new_child

    def add_shallow_copy_of(
        self,
        child_to_add: HConfig,
        *,
        merged: bool = False,
    ) -> HConfig:
        """Add a shallow copy of child_to_add to self.children."""
        new_child = self.add_child(child_to_add.text, return_if_present=merged)
        if merged:
            new_child.instances.append(child_to_add.instance)
        new_child.comments.update(child_to_add.comments)
        new_child.order_weight = child_to_add.order_weight
        if child_to_add.is_leaf:
            new_child.tags_add(child_to_add.tags)
        return new_child

    def instantiate_child(self, text: str) -> HConfig:
        return HConfig(self, text)

    # ------------------------------------------------------------------
    # Child lookup
    # ------------------------------------------------------------------

    def get_child_deep(self, match_rules: tuple[MatchRule, ...]) -> HConfig | None:
        """Find the first child recursively given a tuple of MatchRules."""
        return next(self.get_children_deep(match_rules), None)

    def get_children_deep(
        self,
        match_rules: tuple[MatchRule, ...],
    ) -> Iterator[HConfig]:
        """Find children recursively given a tuple of MatchRules."""
        rule = match_rules[0]
        remaining_rules = match_rules[1:]
        for child in self.get_children(
            equals=rule.equals,
            startswith=rule.startswith,
            endswith=rule.endswith,
            contains=rule.contains,
            re_search=rule.re_search,
        ):
            if remaining_rules:
                yield from child.get_children_deep(remaining_rules)
            else:
                yield child

    def get_child(
        self,
        *,
        equals: str | SetLikeOfStr | None = None,
        startswith: str | tuple[str, ...] | None = None,
        endswith: str | tuple[str, ...] | None = None,
        contains: str | tuple[str, ...] | None = None,
        re_search: str | None = None,
    ) -> HConfig | None:
        """Find a child by text_match rule. If not found, return None."""
        return next(
            self.get_children(
                equals=equals,
                startswith=startswith,
                endswith=endswith,
                contains=contains,
                re_search=re_search,
            ),
            None,
        )

    def get_children(
        self,
        *,
        equals: str | SetLikeOfStr | None = None,
        startswith: str | tuple[str, ...] | None = None,
        endswith: str | tuple[str, ...] | None = None,
        contains: str | tuple[str, ...] | None = None,
        re_search: str | None = None,
    ) -> Iterator[HConfig]:
        """Find all children matching a text_match rule."""
        children_slice = slice(None, None)
        if (
            isinstance(equals, str)
            and startswith is endswith is contains is re_search is None
        ):
            if child := self.children.get(equals):
                yield child
                children_slice = slice(self.children.index(child) + 1, None)
            else:
                return

        elif (
            isinstance(startswith, (str, tuple))
            and equals is endswith is contains is re_search is None
        ):
            duplicates_allowed = None
            for index, child in enumerate(self.children):
                if child.text.startswith(startswith):
                    yield child
                    if duplicates_allowed is None:
                        duplicates_allowed = self._is_duplicate_child_allowed()
                    if duplicates_allowed:
                        children_slice = slice(index + 1, None)
                        break
            else:
                return

        for child in self.children[children_slice]:
            if child.is_match(
                equals=equals,
                startswith=startswith,
                endswith=endswith,
                contains=contains,
                re_search=re_search,
            ):
                yield child

    def all_children_sorted(
        self,
        *,
        key: Callable[[HConfig], Any] | None = None,
    ) -> Iterator[HConfig]:
        """Recursively find and yield all children sorted by order_weight."""
        for child in sorted(self.children, key=key):
            yield child
            yield from child.all_children_sorted(key=key)

    def all_children(self) -> Iterator[HConfig]:
        """Recursively find and yield all children."""
        for child in self.children:
            yield child
            yield from child.all_children()

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    @property
    def tags(self) -> frozenset[str]:
        """Recursive access to tags on all leaf nodes."""
        if self.is_branch:
            found_tags: set[str] = set()
            for child in self.children:
                found_tags.update(child.tags)
            return frozenset(found_tags)
        return frozenset(self._tags)

    @tags.setter
    def tags(self, value: frozenset[str]) -> None:
        """Set tags recursively on all leaf nodes."""
        if self.is_branch:
            for child in self.children:
                child.tags = value
        else:
            self._tags = set(value)

    def tags_add(self, tag: str | Iterable[str]) -> None:
        """Add a tag on all leaf nodes."""
        if self.is_branch:
            for child in self.children:
                child.tags_add(tag)
        elif isinstance(tag, str):
            self._tags.add(tag)
        else:
            self._tags.update(tag)

    def tags_remove(self, tag: str | Iterable[str]) -> None:
        """Remove a tag from all leaf nodes."""
        if self.is_branch:
            for child in self.children:
                child.tags_remove(tag)
        elif isinstance(tag, str):
            self._tags.remove(tag)
        else:
            self._tags.difference_update(tag)

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    def is_match(  # noqa: PLR0911
        self,
        *,
        equals: str | SetLikeOfStr | None = None,
        startswith: str | tuple[str, ...] | None = None,
        endswith: str | tuple[str, ...] | None = None,
        contains: str | tuple[str, ...] | None = None,
        re_search: str | None = None,
    ) -> bool:
        """Return True if ``self.text`` satisfies all supplied criteria."""
        if isinstance(equals, str):
            if self.text != equals:
                return False
        elif (  # pylint: disable=confusing-consecutive-elif
            isinstance(equals, frozenset) and self.text not in equals
        ):
            return False

        if isinstance(startswith, (str, tuple)) and not self.text.startswith(
            startswith
        ):
            return False

        if isinstance(re_search, str) and not search(re_search, self.text):
            return False

        if isinstance(endswith, (str, tuple)) and not self.text.endswith(endswith):
            return False

        if isinstance(contains, str):
            if contains not in self.text:
                return False
        elif isinstance(  # pylint: disable=confusing-consecutive-elif
            contains,
            tuple,
        ) and not any(c in self.text for c in contains):
            return False

        return True

    def is_lineage_match(self, rules: tuple[MatchRule, ...]) -> bool:
        """A generic test against a lineage of HConfig objects."""
        lineage = tuple(self.lineage())
        return len(rules) == len(lineage) and all(
            child.is_match(
                equals=rule.equals,
                startswith=rule.startswith,
                endswith=rule.endswith,
                contains=rule.contains,
                re_search=rule.re_search,
            )
            for (child, rule) in zip(reversed(lineage), reversed(rules), strict=True)
        )

    def is_idempotent_command(self, other_children: Iterable[HConfig]) -> bool:
        """Determine if self.text is an idempotent change."""
        for rule in self.driver.rules.idempotency.idempotent_commands_avoid:
            if self.is_lineage_match(rule.match_rules):
                return False
        return bool(self.driver.idempotent_for(self, other_children))

    # ------------------------------------------------------------------
    # Display / serialization
    # ------------------------------------------------------------------

    def lines(self, *, sectional_exiting: bool = False) -> Iterable[str]:
        if self.is_root:
            for child in sorted(self.children):
                yield from child.lines(sectional_exiting=sectional_exiting)
        else:
            yield self.render()
            for child in sorted(self.children):
                yield from child.lines(sectional_exiting=sectional_exiting)
            if sectional_exiting:
                exit_text, at_node_level = self._sectional_exit_info()
                if exit_text:
                    depth = self.depth() - 1 if at_node_level else self.depth()
                    yield (
                        " " * self.driver.rules.parsing.indentation * depth + exit_text
                    )

    def render(
        self,
        style: TextStyle = "without_comments",
        tag: str | None = None,
    ) -> str:
        """Return a formatted line: indentation_level + text ! comments."""
        comments: list[str] = []
        if style == "without_comments":
            pass
        elif style == "merged":
            instance_count = 0
            instance_comments: set[str] = set()
            for instance in self.instances:
                if tag is None or tag in instance.tags:
                    instance_count += 1
                    instance_comments.update(instance.comments)
            word = "instance" if instance_count == 1 else "instances"
            comments.append(f"{instance_count} {word}")
            comments.extend(instance_comments)
        elif style == "with_comments":
            comments.extend(self.comments)

        comments_str = f" !{', '.join(sorted(comments))}" if comments else ""
        return f"{self.indentation}{self.text}{comments_str}"

    def dump(self) -> Dump:
        """Dump loaded HConfig data."""
        return Dump(
            lines=tuple(
                DumpLine(
                    depth=c.depth(),
                    text=c.text,
                    tags=frozenset(c.tags),
                    comments=frozenset(c.comments),
                    new_in_config=c.new_in_config,
                )
                for c in self.all_children_sorted()
            ),
        )

    def dump_simple(self, *, sectional_exiting: bool = False) -> tuple[str, ...]:
        return tuple(self.lines(sectional_exiting=sectional_exiting))

    def unified_diff(self, target: HConfig) -> Iterator[str]:
        """Yield unified-diff lines comparing self to target."""
        for self_child in self.children:
            self_iter = iter((f"{self_child.indentation}{self_child.text}",))
            if target_child := target.children.get(self_child.text, None):
                found = self_child.unified_diff(target_child)
                if peek := next(found, None):
                    yield from chain(self_iter, (peek,), found)
            else:
                yield f"{self_child.indentation}- {self_child.text}"
                yield from (
                    f"{c.indentation}- {c.text}"
                    for c in self_child.all_children_sorted()
                )
        for target_child in target.children:
            if target_child.text not in self.children:
                yield f"{target_child.indentation}+ {target_child.text}"
                yield from (
                    f"{c.indentation}+ {c.text}"
                    for c in target_child.all_children_sorted()
                )

    # ------------------------------------------------------------------
    # Tree operations (child-oriented)
    # ------------------------------------------------------------------

    def delete(self) -> None:
        """Delete this node from its parent."""
        if self._parent is not None:
            self._parent.children.delete(self)

    def move(self, new_parent: HConfig) -> None:
        """Move this node to a different parent."""
        if self._parent is not None:
            self._parent.children.delete(self)
        new_parent.children.append(self)
        self._parent = new_parent

    def negate(self) -> HConfig:
        """Negate self.text using driver-specific negation rules."""
        return self.driver.negate_child(self)

    def overwrite_with(
        self,
        target: HConfig,
        delta: HConfig,
        *,
        negate: bool = True,
    ) -> None:
        """Overwrite self's section in delta with a deep copy of target."""
        if self.children != target.children:
            if negate:
                if negated := delta.children.get(self.text):
                    negated.negate()
                else:
                    negated = delta.add_child(
                        self.text, check_if_present=False
                    ).negate()
                negated.comments.add("dropping section")
            else:
                delta.children.delete(self.text)
            if self.children:
                new_item = delta.add_deep_copy_of(target)
                new_item.comments.add("re-create section")

    # ------------------------------------------------------------------
    # Sectional rules
    # ------------------------------------------------------------------

    @property
    def sectional_exit(self) -> str | None:
        exit_text, _ = self._sectional_exit_info()
        return exit_text

    def _sectional_exit_info(self) -> tuple[str | None, bool]:
        """Return (exit_text, at_node_level) for this section."""
        for rule in self.driver.rules.sectional.sectional_exiting:
            if self.is_lineage_match(rule.match_rules):
                if exit_text := rule.exit_text:
                    return exit_text, rule.at_node_level
                return None, False
        if not self.children:
            return None, False
        return "exit", False

    def delete_sectional_exit(self) -> None:
        try:
            potential_exit = self.children[-1]
        except IndexError:
            return
        if (exit_text := self.sectional_exit) and exit_text == potential_exit.text:
            potential_exit.delete()

    def use_sectional_overwrite(self) -> bool:
        """Determines if self.text matches a sectional overwrite rule."""
        return any(
            self.is_lineage_match(rule.match_rules)
            for rule in self.driver.rules.sectional.sectional_overwrite
        )

    def use_sectional_overwrite_without_negation(self) -> bool:
        """Check if negation should be handled by overwriting without negating."""
        return any(
            self.is_lineage_match(rule.match_rules)
            for rule in self.driver.rules.sectional.sectional_overwrite_no_negate
        )

    # ------------------------------------------------------------------
    # Config comparison algorithms
    # ------------------------------------------------------------------

    def _future_pre(self, config: HConfig) -> tuple[set[str], set[str]]:
        negated_or_recursed: set[str] = set()
        config_children_ignore: set[str] = set()
        for self_child in self.children:
            if (negation_text := self.root.driver.negate_with(self_child)) and (
                config_child := config.get_child(equals=negation_text)
            ):
                negated_or_recursed.add(self_child.text)
                config_children_ignore.add(config_child.text)
        return negated_or_recursed, config_children_ignore

    def _future(  # noqa: C901
        self,
        config: HConfig,
        future_config: HConfig,
    ) -> None:
        """Recursively compute the future configuration subtree."""
        negated_or_recursed, config_children_ignore = self._future_pre(config)

        for config_child in config.children:
            if config_child.text in config_children_ignore:
                continue
            if (
                config_child.use_sectional_overwrite()
                or config_child.use_sectional_overwrite_without_negation()
            ):
                future_config.add_deep_copy_of(config_child)
            elif self_child := self.root.driver.idempotent_for(
                config_child,
                self.children,
            ):
                future_config.add_deep_copy_of(config_child)
                negated_or_recursed.add(self_child.text)
            elif self_child := self.get_child(equals=config_child.text):
                future_child = future_config.add_shallow_copy_of(self_child)
                self_child._future(config_child, future_child)  # noqa: SLF001
                negated_or_recursed.add(config_child.text)
            elif config_child.text.startswith(self.driver.negation_prefix):
                unnegated_command = config_child.text_without_negation
                if self.get_child(equals=unnegated_command):
                    negated_or_recursed.add(unnegated_command)
                else:
                    future_config.add_shallow_copy_of(config_child)
            elif self_child := self.get_child(
                equals=f"{self.driver.negation_prefix}{config_child.text}",
            ):
                negated_or_recursed.add(self_child.text)
            else:
                future_config.add_deep_copy_of(config_child)

        for self_child in self.children:
            if self_child.text in negated_or_recursed:
                continue
            future_config.add_deep_copy_of(self_child)

    def _config_to_get_to(
        self,
        target: HConfig,
        delta: HConfig,
    ) -> HConfig:
        """Compute commands needed to transition from self to target."""
        self._config_to_get_to_left(target, delta)
        self._config_to_get_to_right(target, delta)
        return delta

    @staticmethod
    def _strip_acl_sequence_number(hier_child: HConfig) -> str:
        words = hier_child.text.split()
        if words[0].isdecimal():
            words.pop(0)
        return " ".join(words)

    def _difference(
        self,
        target: HConfig,
        delta: HConfig,
        target_acl_children: dict[str, HConfig] | None = None,
        *,
        in_acl: bool = False,
    ) -> HConfig:
        acl_sw_matches = tuple(f"ip{x} access-list " for x in ("", "v4", "v6"))

        for self_child in self.children:
            if self_child.text.startswith((self.driver.negation_prefix, "default ")):
                continue

            if in_acl:
                if target_acl_children is None:
                    message = "target_acl_children cannot be None"
                    raise TypeError(message)
                target_child = target_acl_children.get(
                    self._strip_acl_sequence_number(self_child),
                )
            else:
                target_child = target.get_child(equals=self_child.text)

            if target_child is None:
                delta.add_deep_copy_of(self_child)
            else:
                delta_child = delta.add_child(self_child.text)
                if self_child.text.startswith(acl_sw_matches):
                    self_child._difference(  # noqa: SLF001
                        target_child,
                        delta_child,
                        target_acl_children={
                            self._strip_acl_sequence_number(c): c
                            for c in target_child.children
                        },
                        in_acl=True,
                    )
                else:
                    self_child._difference(target_child, delta_child)  # noqa: SLF001
                if not delta_child.children:
                    delta_child.delete()

        return delta

    def _config_to_get_to_left(
        self,
        target: HConfig,
        delta: HConfig,
    ) -> None:
        for self_child in self.children:
            if self_child.text in target.children:
                continue
            if self_child.is_idempotent_command(target.children):
                continue
            negated = delta.add_child(self_child.text).negate()
            if self_child.children:
                negated.comments.add(f"removes {len(self_child.children) + 1} lines")

    def _config_to_get_to_right(
        self,
        target: HConfig,
        delta: HConfig,
    ) -> None:
        for target_child in target.children:
            if self_child := self.children.get(target_child.text):
                if self_child.use_sectional_overwrite():
                    self_child.overwrite_with(target_child, delta)
                    continue
                if self_child.use_sectional_overwrite_without_negation():
                    self_child.overwrite_with(target_child, delta, negate=False)
                    continue
                subtree = delta.instantiate_child(target_child.text)
                self_child._config_to_get_to(target_child, subtree)  # noqa: SLF001
                if subtree.children:
                    delta.children.append(subtree)
            else:
                if target_child.text in delta.children:
                    continue
                new_item = delta.add_deep_copy_of(target_child)
                new_item.new_in_config = True
                for child in new_item.all_children():
                    child.new_in_config = True
                if new_item.children:
                    new_item.comments.add("new section")

    # ------------------------------------------------------------------
    # Root-level operations
    # ------------------------------------------------------------------

    def merge(self, other: HConfig | Iterable[HConfig]) -> HConfig:
        """Merge other HConfig objects into this one."""
        other_configs = (other,) if isinstance(other, HConfig) else other
        for other_config in other_configs:
            for child in other_config.children:
                self.add_deep_copy_of(child, merged=True)
        return self

    def config_to_get_to(
        self,
        target: HConfig,
        delta: HConfig | None = None,
    ) -> HConfig:
        """Compute commands to transition from self to target."""
        if delta is None:
            delta = HConfig(self.driver)
        return self._config_to_get_to(target, delta)

    def difference(self, target: HConfig) -> HConfig:
        """Create a new HConfig with config from self that is not in target."""
        return self._difference(target, HConfig(self.driver))

    def future(self, config: HConfig) -> HConfig:
        """EXPERIMENTAL - predict the future config after config is applied to self."""
        future_config = HConfig(self.driver)
        self._future(config, future_config)
        return future_config

    def with_tags(self, tags: Iterable[str]) -> HConfig:
        """Return a new instance containing only children with a subset of tags."""
        return self._with_tags(frozenset(tags), HConfig(self.driver))

    def deep_copy(self) -> HConfig:
        """Return a deep copy of this object."""
        new_instance = HConfig(self.driver)
        for child in self.children:
            new_instance.add_deep_copy_of(child)
        return new_instance

    def set_order_weight(self) -> HConfig:
        """Set order_weight on all children based on ordering rules."""
        for child in self.all_children():
            for rule in self.driver.rules.ordering:
                if child.is_lineage_match(rule.match_rules):
                    child.order_weight = rule.weight
        return self

    def add_ancestor_copy_of(self, parent_to_add: HConfig) -> HConfig:
        """Add a copy of the ancestry of parent_to_add to self."""
        base: HConfig = self
        for parent in parent_to_add.lineage():
            base = base.add_shallow_copy_of(parent)
        return base

    def all_children_sorted_by_tags(
        self,
        include_tags: Iterable[str],
        exclude_tags: Iterable[str],
    ) -> Iterator[HConfig]:
        """Yield all children recursively that match include/exclude tags."""
        if self.is_root:
            for child in sorted(self.children):
                yield from child.all_children_sorted_by_tags(include_tags, exclude_tags)
        elif self.is_leaf:
            if self.line_inclusion_test(include_tags, exclude_tags):
                yield self
        else:
            self_iter = iter((self,))
            for child in sorted(self.children):
                included_children = child.all_children_sorted_by_tags(
                    include_tags,
                    exclude_tags,
                )
                if peek := next(included_children, None):
                    yield from chain(self_iter, (peek,), included_children)

    # ------------------------------------------------------------------
    # Reporting helpers
    # ------------------------------------------------------------------

    @property
    def instance(self) -> Instance:
        return Instance(
            id=id(self.root),
            comments=frozenset(self.comments),
            tags=frozenset(self.tags),
        )

    def line_inclusion_test(
        self,
        include_tags: Iterable[str],
        exclude_tags: Iterable[str],
    ) -> bool:
        """Determine if this line should be included based on tags."""
        include_line = False
        if include_tags:
            include_line = bool(self.tags.intersection(include_tags))
        if exclude_tags and (include_line or not include_tags):
            return not bool(self.tags.intersection(exclude_tags))
        return include_line

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _is_duplicate_child_allowed(self) -> bool:
        """Determine if duplicate children are allowed under this parent."""
        if self.is_root:
            return False
        return any(
            self.is_lineage_match(rule.match_rules)
            for rule in self.driver.rules.parent_allows_duplicate_child
        )

    def _with_tags(
        self,
        tags: frozenset[str],
        new_instance: HConfig,
    ) -> HConfig:
        """Add children recursively that have a subset of tags."""
        for child in self.children:
            if tags.issubset(child.tags):
                new_child = new_instance.add_shallow_copy_of(child)
                child._with_tags(tags, new_instance=new_child)  # noqa: SLF001
        return new_instance
