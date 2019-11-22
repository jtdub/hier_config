[![Build Status](https://travis-ci.org/netdevops/hier_config.svg?branch=master)](https://travis-ci.org/netdevops/hier_config)
[![CodeFactor](https://www.codefactor.io/repository/github/netdevops/hier_config/badge)](https://www.codefactor.io/repository/github/netdevops/hier_config)

# Hierarchical Configuration

Hierarchical Configuration is a python library that is able to take a running configuration of a network device, compare it to its intended configuration, and build the remediation steps necessary bring a device into spec with its intended configuration.

Hierarchical Configuraiton has been used extensively on:

- [x] Cisco IOS
- [x] Cisco IOSXR
- [x] Cisco NXOS
- [x] Arista EOS

However, any NOS that utilizes a CLI syntax that is structured in a similar fasion to IOS should work mostly out of the box.

The code documentation can be found at: https://netdevops.io/hier_config/

Installation
============

Hierarchical Configuration can be installed directly from github or with pip:

- Github
```
git clone git@github.com:netdevops/hier_config.git
cd hier_config; ./setup.py install
```
- Pip
```
pip install hier-config
```

Basic Usage Example
===================

In the below example, we create two hierarchical configuration objects, load one with a running configuration from a
device, and the other with the intended configuration of the device, then we compare the two objects to derive the
commands necessary to bring the device into spec.

```
## diff between running config and compiled config
$ diff running_config.conf compiled_config.conf
9a10,12
>  name switch_mgmt_10.0.3.0/24
> !
> vlan 4
12a16
>  mtu 9000
15c19,20
<  shutdown
---
>  ip access-group TEST in
>  no shutdown
18a24,30
>  description switch_mgmt_10.0.3.0/24
>  ip address 10.0.3.1 255.255.0.0
>  ip access-group TEST in
>  no shutdown
> !
> interface Vlan4
>  mtu 9000

## file listing
$ ls
compiled_config.conf			test_options_negate_with_undo.yml
running_config.conf			test_tags_ios.yml
test_options_ios.yml

## drop into python shell, get imports, create options dictionary, and create host object
>>> from hier_config import Host
>>> import yaml
>>> options = yaml.load(open('test_options_ios.yml'))
>>> host = Host(hostname='example.rtr', os='ios', hconfig_options=options)

## load running and compiled configs

### loading running config from file
>>> host.load_config_from(config_type="running", name="running_config.conf", load_file=True)
HConfig(host=Host(hostname=example.rtr))

### loading compiled config from string
>>> with open('compiled_config.conf') as f:
...     compiled_config = f.read()
>>> compiled_config
'hostname aggr-example.rtr\n!\nip access-list extended TEST\n 10 permit ip 10.0.0.0 0.0.0.7 any\n!\nvlan 2\n name switch_mgmt_10.0.2.0/24 \n!\nvlan 3\n name switch_mgmt_10.0.3.0/24\n!\nvlan 4\n name switch_mgmt_10.0.4.0/24\n!\ninterface Vlan2\n mtu 9000\n descripton switch_10.0.2.0/24 \n ip address 10.0.2.1 255.255.255.0\n ip access-group TEST in\n no shutdown\n!\ninterface Vlan3\n mtu 9000\n description switch_mgmt_10.0.3.0/24\n ip address 10.0.3.1 255.255.0.0\n ip access-group TEST in\n no shutdown\n!\ninterface Vlan4\n mtu 9000\n description switch_mgmt_10.0.4.0/24\n ip address 10.0.4.1 255.255.0.0\n ip access-group TEST in\n no shutdown\n'

>>> host.load_config_from(config_type="compiled", name=compiled_config, load_file=False)
HConfig(host=Host(hostname=example.rtr))

## loading tags
>>> host.load_tags(name="test_tags_ios.yml", load_file=True)
[{'lineage': [{'equals': ['no ip http secure-server', 'no ip http server', 'vlan', 'no vlan']}], 'add_tags': 'safe'}, {'lineage': [{'startswith': 'interface Vlan'}, {'startswith': ['description']}], 'add_tags': 'safe'}, {'lineage': [{'startswith': ['ip access-list', 'no ip access-list', 'access-list', 'no access-list']}], 'add_tags': 'manual'}, {'lineage': [{'startswith': 'interface Vlan'}, {'startswith': ['ip address', 'no ip address', 'mtu', 'no mtu', 'ip access-group', 'no ip access-group', 'shutdown', 'no shutdown']}], 'add_tags': 'manaual'}]

## building remediation
>>> host.load_remediation()
HConfig(host=Host(hostname=example.rtr))

## displaying remediation
>>> print(host.filter_remediation())
vlan 3
  name switch_mgmt_10.0.3.0/24
vlan 4
  name switch_mgmt_10.0.4.0/24
interface Vlan2
  no shutdown
  mtu 9000
  ip access-group TEST in
interface Vlan3
  description switch_mgmt_10.0.3.0/24
  ip address 10.0.3.1 255.255.0.0
interface Vlan4
  mtu 9000
  description switch_mgmt_10.0.4.0/24
  ip address 10.0.4.1 255.255.0.0
  ip access-group TEST in
  no shutdown
```

The files in the example can be seen in the `tests/files` folder.
