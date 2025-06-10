import time
import ipaddress
import networkx as nx
from typing import Dict, Optional, Tuple

from helper import generate_random_mac

class Packet:
    def __init__(self, src_ip, dst_ip, src_mac, dst_mac, vlan_tag=None, payload=None):
        self.src_ip = src_ip
        self.dst_ip = dst_ip
        self.src_mac = src_mac
        self.dst_mac = dst_mac
        self.vlan_tag = vlan_tag
        self.payload = payload  # Can be "ping", "arp-request", "arp-reply", etc.


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
    def __init__(self, name: str, ip_address: str, vlan: Optional[int] = None, port_id: Optional[int] = None, mac_address: Optional[str] = None):
        self.name = name
        self.ip_address = ip_address
        self.vlan = vlan
        self.port_id = port_id
        self.mac_address = mac_address

    def __repr__(self):
        scope = f"VLAN {self.vlan}" if self.vlan else f"Port {self.port_id}"
        return f"{self.name} ({self.ip_address}, MAC {self.mac_address}) - {scope}"


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
        self.ping_reply_received = False  # Add this line
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
        # Ensure VLAN exists
        if vlan_id not in self.vlan_manager.vlans:
            print(f"\n{self.name}: VLAN {vlan_id} does not exist. Please create it first.\n")
            return

        name = f"VLAN{vlan_id}"
        mac = generate_random_mac()
        iface = L3Interface(name=name, ip_address=ip_with_prefix, vlan=vlan_id, mac_address=mac)
        self.l3_interfaces[name] = iface

        # Add to routing table
        network = ipaddress.ip_interface(ip_with_prefix).network
        self.routing_table[str(network)] = (name, "connected")

        # Add ARP entry for self
        ip = str(ipaddress.ip_interface(ip_with_prefix).ip)
        self.arp_table[ip] = (mac, -1)  # Use -1 to indicate it's a local interface (not tied to a physical port)
        
        # Also update MAC table (use dummy internal port -1 or skip learning)
        self.mac_table[mac] = -1

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

        # Initialize variables
        dst_mac = None
        dst_port = None
        next_hop = None
        route_type = None

        # Step 1: Find route
        for network, (hop, rtype) in self.routing_table.items():
            if ipaddress.ip_address(packet.dst_ip) in ipaddress.ip_network(network):
                next_hop = hop
                route_type = rtype
                break

        if not next_hop:
            print(f"{self.name}: No route to {packet.dst_ip}")
            return False

        # Step 2: If route is 'connected', treat dst_ip directly
        if route_type == "connected":
            dst_ip = packet.dst_ip
            if dst_ip not in self.arp_table:
                # print(f"{self.name}: No ARP entry for {dst_ip}, sending ARP broadcast")
                arp_request = Packet(
                    src_ip=packet.src_ip,
                    dst_ip=packet.dst_ip,
                    src_mac=packet.src_mac,
                    dst_mac="ff:ff:ff:ff:ff:ff",
                    payload={"type": "arp-request", "target_ip": dst_ip}
                )
                # Send ARP request out all ports
                for port in self.ports.values():
                    if port.status == "up" and port.linked_node:
                        neighbor = self.graph.nodes[port.linked_node]["object"]
                        neighbor.receive_packet(arp_request, ttl - 1)
                return True

            dst_mac, port_id = self.arp_table[dst_ip]
            port = self.ports.get(port_id)
            if not port or port.status != "up":
                # print(f"{self.name}: Port {port_id} is down")
                return False

            # Forward packet to destination
            packet.dst_mac = dst_mac
            # print(f"{self.name}: Forwarding to {dst_mac} on port {port_id}")
            neighbor = self.graph.nodes[port.linked_node]["object"]
            return neighbor.receive_packet(packet, ttl - 1)

        # Step 3: If next-hop is another router (static/ospf)
        elif route_type in ("static", "ospf"):
            if next_hop not in self.arp_table:
                # print(f"{self.name}: No ARP for next-hop {next_hop}, sending ARP broadcast")
                arp_request = Packet(
                    src_ip=packet.src_ip,
                    dst_ip=next_hop,
                    src_mac=packet.src_mac,
                    dst_mac="ff:ff:ff:ff:ff:ff",
                    payload={"type": "arp-request", "target_ip": next_hop}
                )
                # Send ARP request out all ports
                for port in self.ports.values():
                    if port.status == "up" and port.linked_node:
                        neighbor = self.graph.nodes[port.linked_node]["object"]
                        neighbor.receive_packet(arp_request, ttl - 1)
                return True

            next_mac, port_id = self.arp_table[next_hop]
            port = self.ports.get(port_id)
            if not port or port.status != "up":
                # print(f"{self.name}: Port {port_id} is down")
                return False

            # Forward packet to next hop
            packet.dst_mac = next_mac
            # print(f"{self.name}: Forwarding to next-hop {next_hop} on port {port_id}")
            neighbor = self.graph.nodes[port.linked_node]["object"]
            return neighbor.receive_packet(packet, ttl - 1)

        else:
            print(f"{self.name}: Unsupported route type {route_type}")
            return False
    
    def receive_packet(self, packet: Packet, ttl: int):
        # print(f"{self.name}: Received packet for {packet.dst_ip} from {packet.src_ip}")

        # Handle TTL expired
        if ttl <= 1:
            print(f"{self.name}: TTL expired for packet to {packet.dst_ip}")
            return False               

        # Step 0: Learn ARP (IP -> MAC) and MAC table (MAC -> Port)
        for port_id, port in self.ports.items():
            if port.status == "up" and port.linked_node:
                neighbor = self.graph.nodes[port.linked_node]["object"]
                neighbor_ips = [
                    ipaddress.ip_interface(iface.ip_address).ip
                    for iface in neighbor.l3_interfaces.values()
                ]
                if ipaddress.ip_address(packet.src_ip) in neighbor_ips:
                    self.arp_table[packet.src_ip] = (packet.src_mac, port_id)
                    self.mac_table[packet.src_mac] = port_id
                    # print(f"{self.name}: Learned ARP {packet.src_ip} → {packet.src_mac} via port {port_id}")
                    break

        # Step 1 : Handle ARP request
        # In the ARP request handling section of receive_packet():
        if packet.payload and isinstance(packet.payload, dict):
            if packet.payload.get("type") == "arp-request":
                target_ip = packet.payload.get("target_ip")
                for iface in self.l3_interfaces.values():
                    if ipaddress.ip_interface(iface.ip_address).ip == ipaddress.ip_address(target_ip):
                        # Create ARP reply
                        arp_reply = Packet(
                            src_ip=target_ip,
                            dst_ip=packet.src_ip,
                            src_mac=iface.mac_address,
                            dst_mac=packet.src_mac,
                            vlan_tag=packet.vlan_tag,
                            payload={"type": "arp-reply", "mac": iface.mac_address}
                        )
                        # print(f"{self.name}: Responding to ARP request for {target_ip}")
                        
                        # Send it back out the port it came in on
                        for port_id, port in self.ports.items():
                            if port.status == "up" and port.linked_node:
                                neighbor = self.graph.nodes[port.linked_node]["object"]
                                if ipaddress.ip_address(packet.src_ip) in [ipaddress.ip_interface(niface.ip_address).ip for niface in neighbor.l3_interfaces.values()]:
                                    return self.send_packet(arp_reply, ttl)
                        return False

        # Step 2: Handle ARP replies
        if packet.payload and isinstance(packet.payload, dict) and packet.payload.get("type") == "arp-reply":
            resolved_mac = packet.payload["mac"]
            # Don't overwrite with -1 — only update if not already learned
            if packet.src_ip not in self.arp_table:
                self.arp_table[packet.src_ip] = (resolved_mac, -1)
            if resolved_mac not in self.mac_table:
                self.mac_table[resolved_mac] = -1

            # print(f"{self.name}: Learned ARP from reply: {packet.src_ip} → {resolved_mac}")
            return True

        # Step 3: Check if this switch is the destination
        # for iface in self.l3_interfaces.values():
        #     if ipaddress.ip_interface(iface.ip_address).ip == ipaddress.ip_address(packet.dst_ip):
        #         print(f"{self.name}: Packet reached destination {packet.dst_ip}")

        # Handle ping echo request
        if packet.payload and isinstance(packet.payload, dict):
            ptype = packet.payload.get("type")

            if ptype == "ping":
                # Find the interface whose IP matches the destination
                for iface in self.l3_interfaces.values():
                    iface_ip = ipaddress.ip_interface(iface.ip_address).ip
                    if iface_ip == ipaddress.ip_address(packet.dst_ip):
                        reply = Packet(
                            src_ip=packet.dst_ip,
                            dst_ip=packet.src_ip,
                            src_mac=iface.mac_address,
                            dst_mac=packet.src_mac,
                            vlan_tag=packet.vlan_tag,
                            payload={"type": "ping-reply", "seq": packet.payload.get("seq")}
                        )
                        return self.send_packet(reply, ttl=10)

            elif ptype == "ping-reply":
                # print(f"{self.name}: Received ping-reply from {packet.src_ip}")
                self.ping_reply_received = True
                return True

        # Step 4: Forward if not for us, decrement ttl by 1
        forwarded = self.send_packet(packet, ttl - 1)
        if not forwarded:
            print(f"{self.name}: Packet could not be forwarded.")
        return forwarded
 

    def ping(self, dst_ip: str, writer, count: int = 4, timeout: float = 1.0):
        writer.write(f"Pinging {dst_ip} with 32 bytes of data:\r\n")

        if not self.l3_interfaces:
            writer.write("No L3 interface available to send ping from.\r\n")
            return

        source_iface = next(iter(self.l3_interfaces.values()))
        src_ip = str(ipaddress.ip_interface(source_iface.ip_address).ip)
        src_mac = source_iface.mac_address or "00:00:00:00:00:01"

        success_count = 0
        rtt_list = []

        for seq in range(1, count + 1):
            self.ping_reply_received = False
            packet = Packet(
                src_ip=src_ip,
                dst_ip=dst_ip,
                src_mac=src_mac,
                dst_mac="ff:ff:ff:ff:ff:ff",
                payload={"type": "ping", "seq": seq}
            )

            send_time = time.time()

            if not self.send_packet(packet, ttl=118):
                writer.write("Request could not be sent.\r\n")
                continue

            while time.time() - send_time < timeout:
                if self.ping_reply_received:
                    rtt = int((time.time() - send_time) * 1000)
                    rtt_list.append(rtt)
                    writer.write(f"Reply from {dst_ip}: bytes=32 time={rtt}ms TTL=118\r\n")
                    success_count += 1
                    break
                time.sleep(0.05)
            else:
                writer.write(f"Request timed out.\r\n")

        # Statistics
        lost = count - success_count
        loss_percent = int((lost / count) * 100)

        writer.write(f"\r\nPing statistics for {dst_ip}:\r\n")
        writer.write(f"    Packets: Sent = {count}, Received = {success_count}, Lost = {lost} ({loss_percent}% loss),\r\n")

        if rtt_list:
            writer.write("Approximate round trip times in milli-seconds:\r\n")
            writer.write(f"    Minimum = {min(rtt_list)}ms, Maximum = {max(rtt_list)}ms, Average = {sum(rtt_list)//len(rtt_list)}ms\r\n")

