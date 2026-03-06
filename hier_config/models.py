from enum import Enum, auto
from typing import Literal

from pydantic import BaseModel as PydanticBaseModel
from pydantic import ConfigDict, NonNegativeInt, PositiveInt

TextStyle = Literal["without_comments", "merged", "with_comments"]


class BaseModel(PydanticBaseModel):
    """Pydantic.BaseModel with a safe config applied."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class DumpLine(BaseModel):
    """A single line from a serialised HConfig tree (see :class:`Dump`)."""

    depth: NonNegativeInt
    text: str
    tags: frozenset[str]
    comments: frozenset[str]
    new_in_config: bool


class MatchRule(BaseModel):
    """Flexible predicate for matching an ``HConfig.text`` value.

    All fields are optional; when multiple are set every criterion must match.
    Used inside all rule types (ordering, idempotency, negation, etc.).
    """

    equals: str | frozenset[str] | None = None
    startswith: str | tuple[str, ...] | None = None
    endswith: str | tuple[str, ...] | None = None
    contains: str | tuple[str, ...] | None = None
    re_search: str | None = None


class TagRule(BaseModel):
    """Rule that applies a set of tags to children matching ``match_rules``."""

    match_rules: tuple[MatchRule, ...]
    apply_tags: frozenset[str]


class SectionalExitingRule(BaseModel):
    """Rule defining the exit command for a hierarchical configuration section.

    When ``at_node_level`` is True, the exit text is rendered at the same
    indentation level as the section itself (e.g. IOS XR ``end-set``).
    When False (the default), it is rendered one level deeper (standard ``exit``).
    """

    match_rules: tuple[MatchRule, ...]
    exit_text: str
    at_node_level: bool = False


class SectionalOverwriteRule(BaseModel):
    """Rule marking a section for full negation + re-creation during remediation."""

    match_rules: tuple[MatchRule, ...]


class SectionalOverwriteNoNegateRule(BaseModel):
    """Rule marking a section for re-creation *without* prior negation."""

    match_rules: tuple[MatchRule, ...]


class OrderingRule(BaseModel):
    """Rule assigning an integer weight to commands to control apply order."""

    match_rules: tuple[MatchRule, ...]
    weight: int


class IndentAdjustRule(BaseModel):
    """Rule defining start/end expressions that shift the indentation level."""

    start_expression: str
    end_expression: str


class ParentAllowsDuplicateChildRule(BaseModel):
    """Rule permitting multiple children with identical text under a parent."""

    match_rules: tuple[MatchRule, ...]


class FullTextSubRule(BaseModel):
    """Regex substitution applied to the entire configuration text block."""

    search: str
    replace: str


class PerLineSubRule(BaseModel):
    """Regex substitution applied to each line of configuration text."""

    search: str
    replace: str


class IdempotentCommandsRule(BaseModel):
    r"""Rule declaring that a command family is idempotent (last value wins).

    When ``key_extract`` is set, the regex is applied to the leaf command text
    and the named group ``key`` is used as the idempotency identity.  This
    makes matching explicit and avoids the heuristic normalisation in the
    default key-generation path.

    Example::

        IdempotentCommandsRule(
            match_rules=(
                MatchRule(startswith="router bgp"),
                MatchRule(re_search=r"neighbor \S+ description"),
            ),
            key_extract=r"neighbor (?P<key>\S+)",
        )

    Here two commands ``neighbor 2.2.2.2 description X`` and
    ``neighbor 3.3.3.3 description Y`` will be keyed by the IP address,
    correctly treating them as *different* idempotent commands.
    """

    match_rules: tuple[MatchRule, ...]
    key_extract: str | None = None


class IdempotentCommandsAvoidRule(BaseModel):
    """Rule preventing specific commands from being treated as idempotent."""

    match_rules: tuple[MatchRule, ...]


class Instance(BaseModel):
    """Metadata snapshot for a single HConfig instance used in merged views."""

    id: PositiveInt
    comments: frozenset[str]
    tags: frozenset[str]


class NegationDefaultWhenRule(BaseModel):
    """Rule specifying when negation should use the ``default`` form."""

    match_rules: tuple[MatchRule, ...]


class NegationDefaultWithRule(BaseModel):
    """Rule replacing negation with a fixed custom command string."""

    match_rules: tuple[MatchRule, ...]
    use: str


SetLikeOfStr = frozenset[str] | set[str]


class Platform(str, Enum):
    """Enumeration of supported network operating system platforms."""

    ARISTA_EOS = auto()
    CISCO_IOS = auto()
    CISCO_NXOS = auto()
    CISCO_XR = auto()
    FORTINET_FORTIOS = auto()
    GENERIC = auto()  # used in cases where the specific platform is unimportant/unknown
    HP_COMWARE5 = auto()
    HP_PROCURVE = auto()
    JUNIPER_JUNOS = auto()
    VYOS = auto()


class Dump(BaseModel):
    """Serialised representation of an entire HConfig tree."""

    lines: tuple[DumpLine, ...]


class ChangeDetail(BaseModel):
    """Detail record for a single remediation change line, optionally nested."""

    line: str
    full_path: tuple[str, ...]
    device_count: NonNegativeInt
    device_ids: frozenset[PositiveInt]
    tags: frozenset[str]
    comments: frozenset[str]
    instances: tuple[Instance, ...]
    children: tuple["ChangeDetail", ...] = ()


class ReportSummary(BaseModel):
    """High-level statistics produced by :class:`RemediationReporter`."""

    total_devices: NonNegativeInt
    total_unique_changes: NonNegativeInt
    most_common_changes: tuple[tuple[str, NonNegativeInt], ...]
    changes_by_tag: dict[str, NonNegativeInt]
