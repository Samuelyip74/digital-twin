import ipaddress
import networkx as nx
from typing import Dict, Optional, Tuple

class Packet:
    def __init__(self, src_ip, dst_ip, src_mac, dst_mac, vlan_tag=None):
        self.src_ip = src_ip
        self.dst_ip = dst_ip
        self.src_mac = src_mac
        self.dst_mac = dst_mac
        self.vlan_tag = vlan_tag


class Port:
    def __init__(self, port_id: int, speed_mbps: int = 100):
        self.port_id = port_id
        self.linked_node: Optional[str] = None
        self.mac_address: Optional[str] = None
        self.ip_address: Optional[str] = None
        self.vlan: int = 1
        self.poe_enabled: bool = False
        self.poe_power_watts: float = 0.0
        self.status: str = "down"
        self.l3_enabled: bool = False
        self.mode: str = "access"
        self.allowed_vlans: set[int] = set()
        self.native_vlan: Optional[int] = None
        self.speed_mbps: int = speed_mbps
        self.mvrp_enabled: bool = False


class L3Interface:
    def __init__(self, name: str, ip_address: str, vlan: Optional[int] = None, port_id: Optional[int] = None):
        self.name = name
        self.ip_address = ip_address
        self.vlan = vlan
        self.port_id = port_id

    def __repr__(self):
        scope = f"VLAN {self.vlan}" if self.vlan else f"Port {self.port_id}"
        return f"{self.name} ({self.ip_address}) - {scope}"


class VLAN:
    def __init__(self, vlan_id: int, name: str = ""):
        self.vlan_id = vlan_id
        self.name = name or f"VLAN{vlan_id}"
        self.ports = set()

    def __repr__(self):
        return f"{self.name} (ID: {self.vlan_id}, Ports: {sorted(self.ports)})"


class VLANManager:
    def __init__(self):
        self.vlans: Dict[int, VLAN] = {}

    def create_vlan(self, vlan_id: int, name: str = ""):
        if vlan_id not in self.vlans:
            self.vlans[vlan_id] = VLAN(vlan_id, name)
            print(f"[VLAN] Created {self.vlans[vlan_id]}")

    def edit_vlan(self, vlan_id: int, name: str):
        if vlan_id in self.vlans:
            self.vlans[vlan_id].name = name

    def delete_vlan(self, vlan_id: int):
        if vlan_id in self.vlans:
            del self.vlans[vlan_id]

    def assign_port(self, vlan_id: int, port_id: int):
        if vlan_id in self.vlans:
            self.vlans[vlan_id].ports.add(port_id)

    def remove_port(self, vlan_id: int, port_id: int):
        if vlan_id in self.vlans:
            self.vlans[vlan_id].ports.discard(port_id)


class OSPFEngine:
    def __init__(self, switch_name: str, reference_bw: int = 100_000):
        self.switch_name = switch_name
        self.reference_bw = reference_bw
        self.lsdb: Dict[str, Dict[str, int]] = {}
        self.routing_table: Dict[str, Tuple[str, int]] = {}

    def get_cost(self, bandwidth_mbps: int) -> int:
        return max(1, self.reference_bw // bandwidth_mbps if bandwidth_mbps else 65535)

    def update_lsdb(self, neighbors: Dict[str, int]):
        self.lsdb[self.switch_name] = neighbors

    def calculate_routes(self):
        G = nx.Graph()
        for router, links in self.lsdb.items():
            for neighbor, cost in links.items():
                G.add_edge(router, neighbor, weight=cost)
        if self.switch_name not in G:
            return
        paths = nx.single_source_dijkstra_path_length(G, self.switch_name)
        for dst, cost in paths.items():
            if dst != self.switch_name:
                self.routing_table[dst] = (dst, cost)

    def get_ospf_routes(self) -> Dict[str, Tuple[str, int]]:
        return self.routing_table

    def show_routing_table(self):
        print(f"[OSPF Routing Table] for {self.switch_name}")
        print("{:<15} {:<10} {:<5}".format("Destination", "Next-Hop", "Cost"))
        for dst, (nexthop, cost) in self.routing_table.items():
            print("{:<15} {:<10} {:<5}".format(dst, nexthop, cost))


class OmniSwitch24:
    def __init__(self, name="OmniSwitch24", timezone="UTC", system_contact="not-set"):
        self.name = name
        self.timezone = timezone
        self.system_contact = system_contact
        self.ports: Dict[int, Port] = {i: Port(i) for i in range(1, 25)}
        self.mac_table: Dict[str, int] = {}
        self.routing_table: Dict[str, Tuple[str, str]] = {}
        self.arp_table: Dict[str, Tuple[str, int]] = {}
        self.l3_interfaces: Dict[str, L3Interface] = {}
        self.vlan_manager = VLANManager()
        self.mvrp_table: Dict[int, set[int]] = {}
        self.graph = nx.Graph()
        self.graph.add_node(self.name)
        self.ospf = OSPFEngine(self.name)

    def set_system_name(self, name: str): self.name = name
    def set_timezone(self, tz: str): self.timezone = tz
    def set_system_contact(self, contact: str): self.system_contact = contact

    def show_system_info(self):
        print("System Information:")
        print(f"  System Name   : {self.name}")
        print(f"  Timezone      : {self.timezone}")
        print(f"  Contact       : {self.system_contact}")

    def add_route(self, ip_cidr: str, next_hop: str):
        self.routing_table[ip_cidr] = (next_hop, "static")

    def create_vlan_interface(self, vlan_id: int, ip_with_prefix: str):
        name = f"VLAN{vlan_id}"
        self.l3_interfaces[name] = L3Interface(name, ip_with_prefix, vlan=vlan_id)
        network = ipaddress.ip_interface(ip_with_prefix).network
        self.routing_table[str(network)] = (f"VLAN{vlan_id}", "connected")

    def assign_l3_interface_to_port(self, port_id: int, ip_with_prefix: str):
        name = f"Port{port_id}"
        self.ports[port_id].l3_enabled = True
        self.ports[port_id].ip_address = ip_with_prefix
        self.l3_interfaces[name] = L3Interface(name, ip_with_prefix, port_id=port_id)
        network = ipaddress.ip_interface(ip_with_prefix).network
        self.routing_table[str(network)] = (f"Port{port_id}", "connected")

    def run_ospf(self):
        neighbors = {}
        for port in self.ports.values():
            if port.status == "up" and port.linked_node:
                cost = self.ospf.get_cost(port.speed_mbps)
                neighbors[port.linked_node] = cost
        self.ospf.update_lsdb(neighbors)
        self.ospf.calculate_routes()
        self.redistribute_ospf_routes()

    def redistribute_ospf_routes(self):
        for dst, (nexthop, cost) in self.ospf.get_ospf_routes().items():
            if dst not in self.routing_table:
                self.routing_table[dst] = (nexthop, "ospf")

    def enable_mvrp_on_port(self, port_id: int):
        self.ports[port_id].mvrp_enabled = True
        self.mvrp_table[port_id] = set()

    def mvrp_advertise(self, neighbor_switch: "OmniSwitch24", via_port_id: int):
        local_vlans = {p.vlan for p in self.ports.values() if p.mode == "access"}
        trunk_port = self.ports[via_port_id]
        if trunk_port.mode != "trunk" or not trunk_port.mvrp_enabled:
            return
        for vlan in local_vlans:
            if vlan not in neighbor_switch.ports[via_port_id].allowed_vlans:
                neighbor_switch.ports[via_port_id].allowed_vlans.add(vlan)
                neighbor_switch.vlan_manager.assign_port(vlan, via_port_id)

    def run_mvrp(self, switch_map: Dict[str, "OmniSwitch24"]):
        for port_id, port in self.ports.items():
            if port.mvrp_enabled and port.mode == "trunk" and port.linked_node in switch_map:
                self.mvrp_advertise(switch_map[port.linked_node], port_id)

    def show_mac_table(self):
        print("MAC Address Table:")
        for mac, entry in self.mac_table.items():
            print(f"  {mac} => Port {entry['port']}")

    def show_arp_table(self):
        print("ARP Table:")
        for ip, mac in self.arp_table.items():
            print(f"  {ip} => {mac}")

    def show_routing_table(self, writer):
        writer.write("Routing Table:\r\n")
        writer.write("Destination        Next-Hop       Type\r\n")
        for destination, (next_hop, route_type) in self.routing_table.items():
            print(destination)
            writer.write(f"{destination:<18} {next_hop:<14} {route_type}\r\n")  # ✅ GOOD

    def show_l3_interfaces(self):
        print("Layer 3 Interfaces:")
        for name, iface in self.l3_interfaces.items():
            print(f"  {name} => {iface.ip_address} (VLAN {iface.vlan if iface.vlan else '-'}, Port {iface.port_id if iface.port_id else '-'})")

    def show_port_status(self, port_id):
        port = self.ports.get(port_id)
        if not port:
            print(f"Port {port_id} not found.")
            return
        print(f"Port {port_id} Status:")
        print(f"  Status: {port.status}")
        print(f"  Mode  : {port.mode}")
        if port.mode == "access":
            print(f"  VLAN  : {port.vlan}")
        elif port.mode == "trunk":
            print(f"  Native VLAN : {port.native_vlan}")
            print(f"  Allowed VLANs: {sorted(port.allowed_vlans)}")

    def show_topology(self):
        print("Topology Links:")
        for port_id, port in self.ports.items():
            if port.linked_node:
                print(f"  Port {port_id} <--> {port.linked_node}")

    def show_ospf_routes(self):
        self.ospf.show_routing_table()


class OmniSwitchTelnetCLI:
    def __init__(self, switch):
        self.switch = switch

    async def interact(self, reader, writer):
        writer.write(f"Welcome to Digital Twin - {self.switch.name} AOS 8.x CLI. Type 'help' to begin.\r\n")

        while True:
            writer.write("> ")
            buffer = ""

            while True:
                char = await reader.read(1)
                if not char:
                    return  # EOF
                if char == '\r':
                    next_char = await reader.read(1)
                    if next_char != '\n':
                        buffer += next_char
                    writer.write("\r\n")
                    break
                elif char in ('\x08', '\x7f'):  # Backspace
                    if buffer:
                        buffer = buffer[:-1]
                        writer.write("\b \b")
                else:
                    buffer += char
                    writer.write(char)

            command = buffer.strip()
            if not command:
                continue

            if command in ("exit", "logout", "quit"):
                writer.write("Goodbye.\r\n")
                await writer.drain()
                writer.close()
                return
            elif command.startswith("set system name "):
                self.switch.set_system_name(command.replace("set system name ", "", 1).strip())
                writer.write("System name updated.\r\n")
            elif command.startswith("set timezone "):
                self.switch.set_timezone(command.replace("set timezone ", "", 1).strip())
                writer.write("Timezone updated.\r\n")
            elif command.startswith("set contact "):
                self.switch.set_system_contact(command.replace("set contact ", "", 1).strip())
                writer.write("System contact updated.\r\n")     
            elif command.startswith("ip static-route "):
                try:
                    _, _, cidr, _, next_hop = command.split()
                    self.switch.add_route(cidr, next_hop)
                    writer.write(f"Command: ip static-route {cidr} gateway {next_hop}\r\n")
                except:
                    writer.write("Usage: ip static-route <CIDR> gateway <next-hop>\r\n")                       
            elif command == "show mac-address-table":
                self.show_mac_table(writer)
            elif command == "show arp":
                self.show_arp_table(writer)
            elif command == "show ip route":
                self.show_routing_table(writer)
            elif command == "show interfaces":
                self.show_all_ports(writer)
            elif command.startswith("interface"):
                try:
                    _, port_str = command.split()
                    self.show_port_status(int(port_str), writer)
                except:
                    writer.write("Usage: interface <port_number>\r\n")
            elif command == "show system":
                self.show_system_info(writer)
            elif command == "show l3 interfaces":
                self.show_l3_interfaces(writer)
            elif command == "show topology":
                self.show_topology(writer)
            elif command == "show ospf routes":
                self.show_ospf_routes(writer)
            elif command == "help":
                writer.write("Available commands:\r\n")
                writer.write("  show mac-address-table\r\n")
                writer.write("  show arp\r\n")
                writer.write("  show ip route\r\n")
                writer.write("  show interfaces\r\n")
                writer.write("  interface <port>\r\n")
                writer.write("  show system\r\n")
                writer.write("  show l3 interfaces\r\n")
                writer.write("  show topology\r\n")
                writer.write("  show ospf routes\r\n")
                writer.write("  exit\r\n")
            else:
                writer.write(f"Unknown command: {command}\r\n")


    def show_mac_table(self, writer):
        writer.write("MAC Address Table:\r\n")
        for mac, entry in self.switch.mac_table.items():
            writer.write(f"  {mac} => Port {entry['port']}\r\n")

    def show_arp_table(self, writer):
        writer.write("ARP Table:\r\n")
        for ip, mac in self.switch.arp_table.items():
            writer.write(f"  {ip} => {mac}\r\n")

    def show_routing_table(self, writer):
        writer.write("Routing Table:\r\n")
        writer.write("Destination        Next-Hop       Type\r\n")
        for destination, (next_hop, route_type) in self.switch.routing_table.items():
            writer.write(f"{destination:<18} {next_hop:<14} {route_type}\r\n")  # ✅ GOOD

    def show_l3_interfaces(self, writer):
        writer.write("Layer 3 Interfaces:\r\n")
        for port, ip in self.switch.l3_interfaces.items():
            writer.write(f"  Port {port} => {ip}\r\n")

    def show_port_status(self, port_id, writer):
        port = self.switch.ports.get(port_id)
        if not port:
            writer.write(f"Port {port_id} not found.\r\n")
            return
        writer.write(f"Port {port_id} Status:\r\n")
        writer.write(f"  Status: {port.status}\r\n")
        writer.write(f"  Mode  : {port.mode}\r\n")
        if port.mode == "access":
            writer.write(f"  VLAN  : {port.vlan}\r\n")
        elif port.mode == "trunk":
            writer.write(f"  Native VLAN : {port.native_vlan}\r\n")
            writer.write(f"  Allowed VLANs: {port.allowed_vlans}\r\n")

    def show_all_ports(self, writer):
        for port_id in sorted(self.switch.ports):
            self.show_port_status(port_id, writer)

    def show_topology(self, writer):
        writer.write("Topology Links:\r\n")
        for port_id, port in self.switch.ports.items():
            if port.linked_node:
                writer.write(f"  Port {port_id} <--> {port.linked_node}\r\n")

    def show_system_info(self, writer):
        writer.write("System Information:\r\n")
        writer.write(f"  Name     : {self.switch.name}\r\n")
        writer.write(f"  Timezone : {self.switch.timezone}\r\n")
        writer.write(f"  Contact  : {self.switch.system_contact}\r\n")

    def show_ospf_routes(self, writer):
        if hasattr(self.switch, 'ospf') and hasattr(self.switch.ospf, 'show_routing_table'):
            self.switch.ospf.show_routing_table(writer)
        else:
            writer.write("OSPF routing not available.\r\n")


