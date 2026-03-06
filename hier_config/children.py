from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar, overload

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from hier_config.root import HConfig

_D = TypeVar("_D")


class HConfigChildren:
    """Ordered collection of `HConfig` objects with fast text-keyed look-up.

    Internally maintains both a `list` (for ordered iteration) and a `dict`
    (for O(1) membership and retrieval by `child.text`).  When duplicate child
    text is allowed by the driver, the mapping stores all occurrences: a single
    child is stored directly, multiple children with the same text are stored
    as a list.  ``get()`` always returns the first occurrence for backward
    compatibility; ``get_all()`` returns all occurrences.
    """

    def __init__(self) -> None:
        self._data: list[HConfig] = []
        self._mapping: dict[str, HConfig | list[HConfig]] = {}

    @overload
    def __getitem__(self, subscript: int | str) -> HConfig: ...

    @overload
    def __getitem__(self, subscript: slice) -> list[HConfig]: ...

    def __getitem__(self, subscript: slice | int | str) -> HConfig | list[HConfig]:
        if isinstance(subscript, slice):
            return self._data[subscript]
        if isinstance(subscript, int):
            return self._data[subscript]
        value = self._mapping[subscript]
        if isinstance(value, list):
            return value[0]
        return value

    def __setitem__(self, index: int, child: HConfig) -> None:
        self._data[index] = child
        self.rebuild_mapping()

    def __contains__(self, item: str) -> bool:
        return item in self._mapping

    def __iter__(self) -> Iterator[HConfig]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, HConfigChildren):
            return NotImplemented

        self_len = len(self._data)
        other_len = len(other._data)
        # Superfast succeed method for no children
        if self_len == other_len == 0:
            return True

        # Superfast fail method
        if self_len != other_len:
            return False

        # Fast fail method
        if self._mapping.keys() != other._mapping.keys():
            return False

        # Slower full comparison
        return all(
            self_child == other_child
            for self_child, other_child in zip(
                sorted(self._data),
                sorted(other._data),
                strict=False,
            )
        )

    def __hash__(self) -> int:
        return hash(
            (*self._data,),
        )

    def _add_to_mapping(self, child: HConfig) -> None:
        """Insert a child into the multimap."""
        key = child.text
        existing = self._mapping.get(key)
        if existing is None:
            self._mapping[key] = child
        elif isinstance(existing, list):
            existing.append(child)
        else:
            self._mapping[key] = [existing, child]

    def append(
        self,
        child: HConfig,
        *,
        update_mapping: bool = True,
    ) -> HConfig:
        self._data.append(child)
        if update_mapping:
            self._add_to_mapping(child)

        return child

    def clear(self) -> None:
        """Delete all children."""
        self._data.clear()
        self._mapping.clear()

    def delete(self, child_or_text: HConfig | str) -> None:
        """Delete a child from self._data and self._mapping.

        When called with a string, all children with that text are removed.
        When called with a child instance, only that specific instance is removed.
        """
        if isinstance(child_or_text, str):
            if child_or_text in self._mapping:
                self._data[:] = [c for c in self._data if c.text != child_or_text]
                del self._mapping[child_or_text]
        else:
            old_len = len(self._data)
            self._data = [c for c in self._data if c is not child_or_text]
            if old_len != len(self._data):
                self.rebuild_mapping()

    def extend(self, children: Iterable[HConfig]) -> None:
        """Add child instances of HConfig."""
        children_list = list(children)
        self._data.extend(children_list)
        for child in children_list:
            self._add_to_mapping(child)

    def get(self, key: str, default: _D | None = None) -> HConfig | _D | None:
        value = self._mapping.get(key)
        if value is None:
            return default
        if isinstance(value, list):
            return value[0]
        return value

    def get_all(self, key: str) -> tuple[HConfig, ...]:
        """Return all children with the given text key.

        Returns an empty tuple if no children match.
        """
        value = self._mapping.get(key)
        if value is None:
            return ()
        if isinstance(value, list):
            return tuple(value)
        return (value,)

    def index(self, child: HConfig) -> int:
        return self._data.index(child)

    def rebuild_mapping(self) -> None:
        """Rebuild self._mapping."""
        self._mapping.clear()
        for child in self._data:
            self._add_to_mapping(child)
