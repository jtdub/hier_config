from abc import ABC, abstractmethod
from collections.abc import Iterable
from ipaddress import IPv4Address, IPv4Interface

from hier_config.platforms.models import (
    InterfaceDot1qMode,
    InterfaceDuplex,
    NACHostMode,
    StackMember,
    Vlan,
)
from hier_config.root import HConfig


class ConfigViewInterfaceBase:  # noqa: PLR0904
    """Base providing a typed view over a single interface config node.

    Properties have default implementations that raise ``NotImplementedError``.
    Platform subclasses override only the properties they support, allowing
    partial implementations without requiring every property.
    """

    def __init__(self, config: HConfig) -> None:
        self.config = config

    @property
    def bundle_id(self) -> str | None:
        """Determine the bundle ID."""
        raise NotImplementedError

    @property
    def bundle_member_interfaces(self) -> Iterable[str]:
        """Determine the member interfaces of a bundle."""
        raise NotImplementedError

    @property
    def bundle_name(self) -> str | None:
        """Determine the bundle name of a bundle member."""
        raise NotImplementedError

    @property
    def description(self) -> str:
        """Determine the interface's description."""
        raise NotImplementedError

    @property
    def dot1q_mode(self) -> InterfaceDot1qMode | None:
        """Derive the configured 802.1Q mode."""
        if self.tagged_all:
            return InterfaceDot1qMode.TAGGED_ALL
        if self.tagged_vlans:
            return InterfaceDot1qMode.TAGGED
        if self.native_vlan and not self.is_svi:
            return InterfaceDot1qMode.ACCESS
        return None

    @property
    def duplex(self) -> InterfaceDuplex:
        """Determine the configured Duplex of the interface."""
        raise NotImplementedError

    @property
    def enabled(self) -> bool:
        """Determines if the interface is enabled."""
        raise NotImplementedError

    @property
    def has_nac(self) -> bool:
        """Determine if the interface has NAC configured."""
        raise NotImplementedError

    @property
    def ipv4_interface(self) -> IPv4Interface | None:
        """Determine the first configured IPv4Interface, address/prefix, object."""
        return next(iter(self.ipv4_interfaces), None)

    @property
    def ipv4_interfaces(self) -> Iterable[IPv4Interface]:
        """Determine the configured IPv4Interface, address/prefix, objects."""
        raise NotImplementedError

    @property
    def is_bundle(self) -> bool:
        """Determine if the interface is a bundle."""
        raise NotImplementedError

    @property
    def is_loopback(self) -> bool:
        """Determine if the interface is a loopback."""
        raise NotImplementedError

    @property
    def is_subinterface(self) -> bool:
        """Determine if the interface is a subinterface."""
        return "." in self.name

    @property
    def is_svi(self) -> bool:
        """Determine if the interface is an SVI."""
        raise NotImplementedError

    @property
    def module_number(self) -> int | None:
        """Determine the module number of the interface."""
        raise NotImplementedError

    @property
    def nac_control_direction_in(self) -> bool:
        """Determine if the interface has NAC 'control direction in' configured."""
        raise NotImplementedError

    @property
    def nac_host_mode(self) -> NACHostMode | None:
        """Determine the NAC host mode."""
        raise NotImplementedError

    @property
    def nac_mab_first(self) -> bool:
        """Determine if the interface has NAC configured for MAB first."""
        raise NotImplementedError

    @property
    def nac_max_dot1x_clients(self) -> int:
        """Determine the max dot1x clients."""
        raise NotImplementedError

    @property
    def nac_max_mab_clients(self) -> int:
        """Determine the max mab clients."""
        raise NotImplementedError

    @property
    def name(self) -> str:
        """Determine the name of the interface."""
        raise NotImplementedError

    @property
    def native_vlan(self) -> int | None:
        """Determine the native VLAN."""
        raise NotImplementedError

    @property
    def number(self) -> str:
        """Remove letters from the interface name, leaving just numbers and symbols."""
        raise NotImplementedError

    @property
    def parent_name(self) -> str | None:
        """Determine the parent bundle interface name."""
        raise NotImplementedError

    @property
    def poe(self) -> bool:
        """Determine if PoE is enabled."""
        raise NotImplementedError

    @property
    def port_number(self) -> int:
        """Determine the interface port number."""
        raise NotImplementedError

    @property
    def speed(self) -> tuple[int, ...] | None:
        """Determine the statically allowed speeds the interface can operate at. In Mbps."""
        raise NotImplementedError

    @property
    def subinterface_number(self) -> int | None:
        """Determine the sub-interface number."""
        raise NotImplementedError

    @property
    def tagged_all(self) -> bool:
        """Determine if all the VLANs are tagged."""
        raise NotImplementedError

    @property
    def tagged_vlans(self) -> tuple[int, ...]:
        """Determine the tagged VLANs."""
        raise NotImplementedError

    @property
    def vrf(self) -> str:
        """Determine the VRF."""
        raise NotImplementedError

    @property
    def _bundle_prefix(self) -> str:
        raise NotImplementedError


class HConfigViewBase(ABC):
    """Abstract base providing a structured view over a full HConfig tree.

    Platform-specific subclasses (e.g. ``HConfigViewCiscoIOS``) implement
    ``interface_views`` to yield :class:`ConfigViewInterfaceBase` objects and
    ``dot1q_mode_from_vlans`` to interpret 802.1Q mode from VLAN data.

    Properties have default implementations that raise ``NotImplementedError``
    where appropriate. Only ``interface_views`` and ``interfaces`` remain
    abstract as they are required for the base class helpers to function.
    """

    def __init__(self, config: HConfig) -> None:
        self.config = config

    @property
    def bundle_interface_views(self) -> Iterable[ConfigViewInterfaceBase]:
        for interface_view in self.interface_views:
            if interface_view.is_bundle:
                yield interface_view

    def dot1q_mode_from_vlans(
        self,
        untagged_vlan: int | None = None,
        tagged_vlans: tuple[int, ...] = (),
        *,
        tagged_all: bool = False,
    ) -> InterfaceDot1qMode | None:
        raise NotImplementedError

    @property
    def hostname(self) -> str | None:
        raise NotImplementedError

    @property
    def interface_names_mentioned(self) -> frozenset[str]:
        """Returns a set with all the interface names mentioned in the config."""
        raise NotImplementedError

    def interface_view_by_name(self, name: str) -> ConfigViewInterfaceBase | None:
        for interface_view in self.interface_views:
            if interface_view.name == name:
                return interface_view
        return None

    @property
    @abstractmethod
    def interface_views(self) -> Iterable[ConfigViewInterfaceBase]:
        pass

    @property
    @abstractmethod
    def interfaces(self) -> Iterable[HConfig]:
        pass

    @property
    def interfaces_names(self) -> Iterable[str]:
        for interface_view in self.interface_views:
            yield interface_view.name

    @property
    def ipv4_default_gw(self) -> IPv4Address | None:
        raise NotImplementedError

    @property
    def location(self) -> str:
        raise NotImplementedError

    @property
    def module_numbers(self) -> Iterable[int]:
        seen: set[int] = set()
        for interface_view in self.interface_views:
            if module_number := interface_view.module_number:
                if module_number in seen:
                    continue
                seen.add(module_number)
                yield module_number

    @property
    def stack_members(self) -> Iterable[StackMember]:
        """Determine the configured stack members."""
        raise NotImplementedError

    @property
    def vlan_ids(self) -> frozenset[int]:
        """Determine the VLAN IDs."""
        return frozenset(vlan.id for vlan in self.vlans)

    @property
    def vlans(self) -> Iterable[Vlan]:
        """Determine the configured VLANs."""
        raise NotImplementedError
