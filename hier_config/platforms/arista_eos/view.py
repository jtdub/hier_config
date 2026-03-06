from collections.abc import Iterable

from hier_config.platforms.view_base import (
    ConfigViewInterfaceBase,
    HConfigViewBase,
)
from hier_config.root import HConfig


class ConfigViewInterfaceAristaEOS(ConfigViewInterfaceBase):  # pylint: disable=abstract-method
    """Interface config view for Arista EOS.

    Only partially implemented — properties not overridden here inherit the
    default ``NotImplementedError`` from the base class.
    """

    @property
    def is_subinterface(self) -> bool:
        return "." in self.name

    @property
    def port_number(self) -> int:
        return int(self.name.split("/")[-1].split(".")[0])


class HConfigViewAristaEOS(HConfigViewBase):
    """Full-tree config view for Arista EOS."""

    @property
    def hostname(self) -> str | None:
        if child := self.config.get_child(startswith="hostname "):
            return child.text.split()[1].lower()
        return None

    @property
    def interface_views(self) -> Iterable[ConfigViewInterfaceAristaEOS]:
        for interface in self.interfaces:
            yield ConfigViewInterfaceAristaEOS(interface)

    @property
    def interfaces(self) -> Iterable[HConfig]:
        return self.config.get_children(startswith="interface ")
