import attr
import collections
import yaml


def setup_yaml():
    """ http://stackoverflow.com/a/8661021 """
    represent_dict_order = (
        lambda self, data: self.represent_mapping('tag:yaml.org,2002:map',
                                                  data.items()))
    yaml.add_representer(collections.OrderedDict, represent_dict_order)


setup_yaml()


def asdict(inst):
    r = collections.OrderedDict()
    for field in attr.fields(type(inst)):
        if field.name.startswith('_'):
            continue
        v = getattr(inst, field.name)
        if v:
            if hasattr(v, 'id'):
                v = v.id
            if v is not None:
                r[field.name] = v
    return r


@attr.s
class NetInterface():
    addresses = attr.ib(default=attr.Factory(list))
    dhcp4 = attr.ib(default=False)
    dhcp6 = attr.ib(default=False)
    gateway4 = attr.ib(default=None)
    gateway6 = attr.ib(default=None)
    _config = attr.ib(default=None)
    macadddress = attr.ib(default=None)
    match = attr.ib(default=attr.Factory(dict))
    _name = attr.ib(default=None)
    nameservers = attr.ib(default=attr.Factory(dict))
    routes = attr.ib(default=attr.Factory(list))
    _type = attr.ib(default=None)

    @classmethod
    def from_config(cls, config):
        netif = NetInterface(config=config)
        for k, v in config.items():
            setattr(netif, k, v)

        return netif

    def update_config(self, config):
        for k, v in config.items():
            setattr(self, k, v)

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value

    @property
    def type(self):
        return self._type

    @type.setter
    def type(self, value):
        self._type = value


@attr.s
class Ethernet(NetInterface):
    wakeonlan = attr.ib(default=False)

    @classmethod
    def from_config(cls, config=None):
        if not config:
            config = {}
        eth = Ethernet(config=config)
        eth.type = 'ethernets'
        for k, v in config.items():
            setattr(eth, k, v)
        if eth.macaddress:
            eth.match = {'macaddress': eth.macaddress}
        return eth


@attr.s
class Wifi(NetInterface):
    access_points = attr.ib(default=attr.Factory(dict))
    _wifi_modes = ['adhoc', 'ap', 'infrastructure']

    @classmethod
    def from_config(cls, config=None):
        if not config:
            config = {}
        ssid = config.get('ssid')
        if not ssid:
            raise ValueError('Wifi requires ssid parameter')
        wifi = Wifi(config=config)
        wifi.type = 'wifis'
        for k, v in config.items():
            if k in ['ssid', 'password', 'mode']:
                continue
            setattr(wifi, k, v)
        apcfg = {}
        if config.get('password'):
            apcfg['password'] = config.get('password')
        if config.get('mode'):
            mode = config.get('mode')
            if mode not in cls._wifi_modes:
                raise ValueError('Wifi mode "%s" not one of "%s"',
                                 mode, cls._wifi_modes)
            apcfg['mode'] = mode
        wifi.access_points[ssid] = apcfg
        return wifi


@attr.s
class Vlan(NetInterface):
    id = attr.ib(default=None)
    link = attr.ib(default=None)

    @classmethod
    def from_config(cls, config=None):
        if not config:
            config = {}
        vlan = Vlan(config=config)
        vlan.type = 'vlans'
        for k, v in config.items():
            setattr(vlan, k, v)
        vlan.name = "%s.%s" % (vlan.link, vlan.id)
        return vlan


@attr.s
class Bridge(NetInterface):
    interfaces = attr.ib(default=attr.Factory(list))
    parameters = attr.ib(default=attr.Factory(dict))

    @classmethod
    def from_config(cls, config=None):
        if not config:
            config = {}
        br = Bridge(config=config)
        br.type = 'bridges'
        for k, v in config.items():
            setattr(br, k, v)
        return br


@attr.s
class Bond(NetInterface):
    interfaces = attr.ib(default=attr.Factory(list))
    parameters = attr.ib(default=attr.Factory(dict))

    @classmethod
    def from_config(cls, config=None):
        if not config:
            config = {}
        bond = Bond(config=config)
        bond.type = 'bonds'
        for k, v in config.items():
            setattr(bond, k, v)
        return bond


def render(config):
    netplan = collections.OrderedDict()
    netplan['version'] = 2
    for iface, nc in config.items():
        section_name = nc.type
        section = netplan.get(section_name, {})
        section[nc.name] = asdict(nc)
        netplan.update({section_name: section})

    r = {'network': netplan}
    print(yaml.dump(r, default_flow_style=False, indent=2))


if __name__ == "__main__":
    network_config = {}

    eth = Ethernet.from_config(config={'name': 'eno3',
                                       'macaddress': 'aa:bb:cc:dd:ee:ff',
                                       'mtu': 1500,
                                       'dhcp4': True})
    eth.dhcp6 = True
    network_config[eth.name] = eth

    eth1 = Ethernet.from_config(config={'name': 'eth1',
                                        'macaddress': "01:23:45:56:78"})
    network_config[eth1.name] = eth1

    vlink = Vlan.from_config(config={'id': 23, 'link': eth.name})
    vlink.addresses.append('192.168.23.10/24')
    vlink.addresses.append('10.168.232.2/29')
    vlink.gateway4 = '192.168.23.1'
    vlink.nameservers = {'addresses': ['192.168.23.2', '8.8.8.8'],
                         'search': ['mydomain.io']}
    network_config[vlink.name] = vlink

    br0 = Bridge.from_config(config={'name': 'br0', 'mtu': 9000,
                                     'interfaces': ['eth1'],
                                     'parameters': {'stp': False}})
    br0.addresses.append('192.168.122.1/24')
    network_config[br0.name] = br0

    wlan0 = Wifi.from_config(config={'name': 'wlan0',
                                     'ssid': 'MyAP',
                                     'password': 'mypassword',
                                     'mode': 'adhoc',
                                     'macaddress': "00:11:22:33:44:55"})
    wlan0.dhcp4 = True
    network_config[wlan0.name] = wlan0

    bond1 = Bond.from_config(config={'name': 'bond1', 'mtu': 4500,
                                     'interfaces': ['eth6', 'eth7'],
                                     'parameters': {'mode': '802.3ad',
                                                    'lacp-rate': 'fast'}})
    bond1.dhcp6 = True
    network_config[bond1.name] = bond1

    render(network_config)
    vlink.update_config({'addresses': None, 'gateway4': None, 'dhcp6': True,
                        'nameservers': []})
    print('---- Updated ----')
    render(network_config)
