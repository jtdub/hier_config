# Hierarchical Configuration

Hierarchical Configuration, also known as `hier_config`, is a Python library designed to query and compare network device configurations. Among other capabilities, it can compare the running config to an intended configuration to determine the commands necessary to bring a device into compliance.

## Why hier_config?

Network devices continuously drift from their intended state — VLANs appear, ACL entries change, BGP timers shift.  hier_config solves this by parsing configuration text into a hierarchical tree and performing deterministic, line-level diffs that respect the vendor's own syntax rules.  Rather than string-matching raw text, it understands the structure of commands so that remediation output is minimal, ordered, and safe to apply.

## Supported Platforms

- Cisco IOS, IOS XR, NX-OS
- Arista EOS
- Fortinet FortiOS
- HP ProCurve (Aruba AOSS), HP Comware5
- Juniper JunOS *(experimental)*
- VyOS *(experimental)*

Hier Config is compatible with any NOS that uses a structured CLI syntax similar to Cisco IOS or JunOS.

## Installation

```shell
pip install hier-config
```

## Quick Start

```python
from hier_config import WorkflowRemediation, get_hconfig, Platform

running = get_hconfig(Platform.CISCO_IOS, running_config_text)
intended = get_hconfig(Platform.CISCO_IOS, intended_config_text)
workflow = WorkflowRemediation(running, intended)

for line in workflow.remediation_config.all_children_sorted():
    print(line.render())
```

## Documentation

Full documentation is available at [hier-config.readthedocs.io](https://hier-config.readthedocs.io/en/latest/), including:

- [Getting Started](https://hier-config.readthedocs.io/en/latest/getting-started/) — walk through a first diff
- [Drivers](https://hier-config.readthedocs.io/en/latest/drivers/) — platform-specific behavior
- [Working with Tags](https://hier-config.readthedocs.io/en/latest/tags/) — filter remediation output
- [Future Config](https://hier-config.readthedocs.io/en/latest/future-config/) — predict post-change state
- [Config View](https://hier-config.readthedocs.io/en/latest/config-view/) — typed interface data
- [Remediation Reporting](https://hier-config.readthedocs.io/en/latest/remediation-reporting/) — fleet-wide analysis
- [Architecture](https://hier-config.readthedocs.io/en/latest/architecture/) — how it all fits together
- [v3 to v4 Migration](https://hier-config.readthedocs.io/en/latest/migration-guide/) — upgrade guide
