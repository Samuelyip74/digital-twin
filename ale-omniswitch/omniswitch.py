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

    def show_vlan(self):
        if not self.vlans:
            print("No VLANs configured.")
            return
        print("VLAN ID    Name        Ports")
        print("-----------------------------")
        for vlan_id in sorted(self.vlans):
            vlan = self.vlans[vlan_id]
            ports = ','.join(map(str, sorted(vlan.ports))) if vlan.ports else "-"
            print(f"{vlan_id:<10} {vlan.name:<10} {ports}")


    def create_vlan(self, vlan_id: int, name: str = ""):
        if vlan_id not in self.vlans:
            self.vlans[vlan_id] = VLAN(vlan_id, name)
            

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


class OmniSwitch:
    def __init__(self, name="OmniSwitch", timezone="UTC", system_contact="not-set"):
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

    def remove_route(self, ip_cidr: str):
        if ip_cidr in self.routing_table:
            del self.routing_table[ip_cidr]
            print(f"Route {ip_cidr} removed.")
        else:
            print(f"Route {ip_cidr} not found.")

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

    def mvrp_advertise(self, neighbor_switch: "OmniSwitch", via_port_id: int):
        local_vlans = {p.vlan for p in self.ports.values() if p.mode == "access"}
        trunk_port = self.ports[via_port_id]
        if trunk_port.mode != "trunk" or not trunk_port.mvrp_enabled:
            return
        for vlan in local_vlans:
            if vlan not in neighbor_switch.ports[via_port_id].allowed_vlans:
                neighbor_switch.ports[via_port_id].allowed_vlans.add(vlan)
                neighbor_switch.vlan_manager.assign_port(vlan, via_port_id)

    def run_mvrp(self, switch_map: Dict[str, "OmniSwitch"]):
        for port_id, port in self.ports.items():
            if port.mvrp_enabled and port.mode == "trunk" and port.linked_node in switch_map:
                self.mvrp_advertise(switch_map[port.linked_node], port_id)

    def show_mac_table(self):
        print("MAC Address Table:")
        for mac, entry in self.mac_table.items():
            print(f"  {mac} => Port {entry['port']}")

    def show_arp_table(self):
        print("ARP Table:")
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

    def send_packet(self, packet: Packet, ttl: int = 10):
        if ttl <= 0:
            print(f"{self.name}: TTL expired for packet to {packet.dst_ip}")
            return False

        # 1. Check routing table
        next_hop = None
        for network in self.routing_table:
            if ipaddress.ip_address(packet.dst_ip) in ipaddress.ip_network(network):
                next_hop, route_type = self.routing_table[network]
                break

        if not next_hop:
            print(f"{self.name}: No route to {packet.dst_ip}")
            return False

        # 2. If directly connected (e.g. PortX or VLANX)
        if next_hop.startswith("Port") or next_hop.startswith("VLAN"):
            # Check ARP
            if packet.dst_ip in self.arp_table:
                dst_mac, port_id = self.arp_table[packet.dst_ip]
                port = self.ports[port_id]

                if port.status != "up":
                    print(f"{self.name}: Port {port_id} is down")
                    return False

                packet.dst_mac = dst_mac

                # Check MAC table
                if dst_mac in self.mac_table:
                    dst_port = self.mac_table[dst_mac]
                    dst_port_obj = self.ports.get(dst_port)
                    if dst_port_obj and dst_port_obj.status == "up" and dst_port_obj.linked_node:
                        print(f"{self.name}: Forwarding packet to {dst_mac} on port {dst_port}")
                        next_switch = self.graph.nodes[dst_port_obj.linked_node]["object"]
                        return next_switch.receive_packet(packet, ttl - 1)
                    else:
                        print(f"{self.name}: Destination port {dst_port} is down or unlinked")
                        return False
                else:
                    print(f"{self.name}: MAC {dst_mac} not in MAC table")
                    return False
            else:
                print(f"{self.name}: No ARP entry for {packet.dst_ip}, sending ARP broadcast")
                # Simulate ARP broadcast: add dummy MAC
                dummy_mac = "de:ad:be:ef:00:01"
                self.arp_table[packet.dst_ip] = (dummy_mac, 1)  # Assume discovered on port 1
                self.mac_table[dummy_mac] = 1
                return self.send_packet(packet, ttl - 1)

        # 3. Next-hop forwarding
        elif next_hop in self.graph:
            for port_id, port in self.ports.items():
                if port.status == "up" and port.linked_node == next_hop:
                    print(f"{self.name}: Routing to next-hop {next_hop} via port {port_id}")
                    next_switch = self.graph.nodes[next_hop]["object"]
                    return next_switch.receive_packet(packet, ttl - 1)
            print(f"{self.name}: No port to reach next-hop {next_hop}")
            return False

        else:
            print(f"{self.name}: Unknown next-hop {next_hop}")
            return False
    
    
    def receive_packet(self, packet: Packet, ttl: int):
        print(f"{self.name}: Received packet for {packet.dst_ip}")
        # Check if destination matches one of our L3 interfaces
        for iface in self.l3_interfaces.values():
            if ipaddress.ip_interface(iface.ip_address).ip == ipaddress.ip_address(packet.dst_ip):
                print(f"{self.name}: Packet reached destination {packet.dst_ip}")
                return True
        return self.send_packet(packet, ttl)    

    def ping(self, dst_ip: str):
        print(f"Pinging {dst_ip} from {self.name}...")

        packet = Packet(
            src_ip="0.0.0.0",  # Replace this with an appropriate source IP if available
            dst_ip=dst_ip,
            src_mac="00:11:22:33:44:55",
            dst_mac="ff:ff:ff:ff:ff:ff"
        )

        success_count = 0
        for i in range(5):
            print(f"Ping {i+1}...")
            if self.send_packet(packet, ttl=10):
                print(f"Reply from {dst_ip}")
                success_count += 1
            else:
                print(f"Request timeout for {dst_ip}")

        print(f"Ping statistics: {success_count}/5 received.")



