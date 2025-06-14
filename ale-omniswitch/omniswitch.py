import time
from collections import defaultdict, deque
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
        self.neighbors = {}
        self.connected_subnets: set[str] = set()  # ✅ Add this line        

    def get_cost(self, bandwidth_mbps: int) -> int:
        return max(1, self.reference_bw // bandwidth_mbps if bandwidth_mbps else 65535)

    def update_lsdb(self, neighbors: Dict[str, int]):
        self.lsdb[self.switch_name] = neighbors

    def calculate_routes(self, current_switch: "OmniSwitch"):
        G = nx.Graph()
        for router, links in self.lsdb.items():
            for neighbor, cost in links.items():
                G.add_edge(router, neighbor, weight=cost)

        if self.switch_name not in G:
            return

        paths = nx.single_source_dijkstra_path(G, self.switch_name)
        self.routing_table.clear()

        for dst_router, path in paths.items():
            if dst_router == self.switch_name:
                continue

            next_hop_router = path[1]

            # Find IP of next-hop from current switch to that neighbor
            next_hop_ip = current_switch._get_next_hop_ip_to(next_hop_router)
            if not next_hop_ip:
                # print(f"[{self.switch_name}] Could not determine next hop IP to {next_hop_router}") 
                continue

            # Import that router's connected networks
            neighbor_obj = current_switch.graph.nodes[dst_router]["object"]
            for subnet in neighbor_obj.ospf.connected_subnets:
                # print(f"[{self.switch_name}] Adding OSPF route: {subnet} via {next_hop_ip}")
                if subnet not in self.routing_table:
                    self.routing_table[subnet] = (next_hop_ip, cost)
                    # print(f"[{self.switch_name}] Adding OSPF route: {subnet} via {next_hop_ip}")


    def get_ospf_routes(self) -> Dict[str, Tuple[str, int]]:
        return self.routing_table

    def show_routing_table(self):
        print(f"[OSPF Routing Table] for {self.switch_name}")
        print("{:<15} {:<10} {:<5}".format("Destination", "Next-Hop", "Cost"))
        for dst, (nexthop, cost) in self.routing_table.items():
            print("{:<15} {:<10} {:<5}".format(dst, nexthop, cost)) 


class OmniSwitch:
    def __init__(self, name="OmniSwitch", timezone="UTC", system_contact="not-set"):
        self.debug = False
        self.ping_reply_received = False  # Add this line
        self.arp_queue = defaultdict(deque)  # dst_ip -> deque of (packet, ttl, timestamp)
        self.arp_request_timestamps = {}     # dst_ip -> last_request_time        
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

    # Helper class
    def _learn_arp(self, packet: Packet, in_port_id: int):
        if in_port_id is None or in_port_id not in self.ports:
            return

        # Only learn from ARP packets
        if not self._is_arp_request(packet) and not self._is_arp_reply(packet):
            return

        self.debug and print(f"{self.name}: _learn_arp called with in_port_id={in_port_id} for {packet.src_ip} → {packet.src_mac}")

        self.arp_table[packet.src_ip] = (packet.src_mac, in_port_id)
        self.mac_table[packet.src_mac] = in_port_id

        self.debug and print(f"{self.name}: Learned ARP {packet.src_ip} → {packet.src_mac} on port {in_port_id}")


    def _is_arp_request(self, packet: Packet) -> bool:
        return isinstance(packet.payload, dict) and packet.payload.get("type") == "arp-request"

    def _handle_arp_request(self, packet: Packet, ttl: int, in_port_id: int) -> bool:
        target_ip = packet.payload.get("target_ip")

        # Step 1: Check if this switch owns the target IP
        for iface in self.l3_interfaces.values():
            if ipaddress.ip_interface(iface.ip_address).ip == ipaddress.ip_address(target_ip):
                self.debug and print(f"{self.name}: Replying to ARP request for {target_ip} for port {in_port_id}")

                # Build ARP reply
                arp_reply = Packet(
                    src_ip=target_ip,
                    dst_ip=packet.src_ip,
                    src_mac=iface.mac_address,
                    dst_mac=packet.src_mac,
                    vlan_tag=packet.vlan_tag,
                    payload={"type": "arp-reply", "mac": iface.mac_address}
                )

                # Send reply using proper routing logic
                return self.send_packet(arp_reply, ttl - 1)

        # Step 2: Flood the ARP request to all other ports
        for port in self.ports.values():
            if port.status == "up" and port.linked_node and port.port_id != in_port_id:
                self.debug and print(f"{self.name}: Port: {port.port_id}, Neighbor: {port.linked_node}")
                neighbor = self.graph.nodes[port.linked_node]["object"]

                # Find the reverse port (on neighbor) that links back to this switch
                for nbr_port_id, nbr_port in neighbor.ports.items():
                    if nbr_port.linked_node == self.name:
                        self.debug and print(f"{self.name}: Flooding ARP request for {target_ip} to neighbor {neighbor.name} port {nbr_port_id}")
                        neighbor.receive_packet(packet, ttl - 1, in_port_id=nbr_port_id)
                        break  # only break inner loop, continue flooding other neighbors


        return True



    def _is_arp_reply(self, packet: Packet) -> bool:
        return isinstance(packet.payload, dict) and packet.payload.get("type") == "arp-reply"

    def _handle_arp_reply(self, packet: Packet, in_port_id: int):
        sender_ip = packet.src_ip
        sender_mac = packet.src_mac
        self.debug and print(f"{self.name}: Learned ARP from reply: {sender_ip} → {sender_mac} via port {in_port_id}")

        self.arp_table[sender_ip] = (sender_mac, in_port_id)
        self.mac_table[sender_mac] = in_port_id

        # Process queued packets
        if sender_ip in self.arp_queue:
            queued = list(self.arp_queue.pop(sender_ip))
            for queued_packet, queued_ttl, timestamp in queued:
                if time.time() - timestamp <= 5:
                    self.debug and print(f"{self.name}: Sending queued packet to {sender_ip}")
                    self._handle_connected_route(queued_packet, queued_ttl)
                else:
                    self.debug and print(f"{self.name}: Dropped expired queued packet to {sender_ip}")


    def _is_local_destination(self, dst_ip: str) -> bool:
        self.debug and print(f"dst_ip is {dst_ip}")
        for iface in self.l3_interfaces.values():
            if ipaddress.ip_address(dst_ip) == ipaddress.ip_interface(iface.ip_address).ip:
                return True
        return False

    def _is_ping(self, packet: Packet) -> bool:
        return isinstance(packet.payload, dict) and packet.payload.get("type") == "ping"

    def _handle_ping(self, packet: Packet, ttl: int) -> bool:
        for iface in self.l3_interfaces.values():
            if ipaddress.ip_interface(iface.ip_address).ip == ipaddress.ip_address(packet.dst_ip):
                reply = Packet(
                    src_ip=packet.dst_ip,
                    dst_ip=packet.src_ip,
                    src_mac=iface.mac_address,
                    dst_mac=packet.src_mac,
                    vlan_tag=packet.vlan_tag,
                    payload={"type": "ping-reply", "seq": packet.payload.get("seq")}
                )
                return self.send_packet(reply, ttl=10)
        return False

    def _is_ping_reply(self, packet: Packet) -> bool:
        return isinstance(packet.payload, dict) and packet.payload.get("type") == "ping-reply"

    def _handle_ping_reply(self) -> bool:
        self.ping_reply_received = True
        return True

    def _forward(self, packet: Packet, ttl: int, exclude_port: int = None) -> bool:
        forwarded = self.send_packet(packet, ttl - 1, exclude_port=exclude_port)
        if not forwarded:
            self.debug and print(f"{self.name}: Packet could not be forwarded.")
        return forwarded
            
    def _lookup_route(self, dst_ip: str):
        for network, (next_hop, route_type) in self.routing_table.items():
            if ipaddress.ip_address(dst_ip) in ipaddress.ip_network(network):
                return next_hop, route_type
        return None, None

    def _send_arp_request(self, target_ip: str, src_ip: str, src_mac: str, ttl: int, exclude_port: int = None):
        arp_request = Packet(
            src_ip=src_ip,
            dst_ip=target_ip,
            src_mac=src_mac,
            dst_mac="ff:ff:ff:ff:ff:ff",
            payload={"type": "arp-request", "target_ip": target_ip}
        )
        for port in self.ports.values():
            if port.status == "up" and port.linked_node:
                neighbor = self.graph.nodes[port.linked_node]["object"]
                for nbr_port_id, nbr_port in neighbor.ports.items():
                    if nbr_port.linked_node == self.name:
                        neighbor.receive_packet(arp_request, ttl - 1, in_port_id=nbr_port_id)
                        self.debug and print(f"{self.name}: Send packet from Port {port.port_id} to {port.linked_node}, incoming port {nbr_port_id}.")

    def _valid_port(self, port_id: int) -> Optional[Tuple['Port', 'OmniSwitch']]:
        port = self.ports.get(port_id)
        if port and port.status == "up" and port.linked_node:
            neighbor = self.graph.nodes[port.linked_node]["object"]
            return port, neighbor
        return None


    def _handle_connected_route(self, packet: Packet, ttl: int, exclude_port: int = None):
        dst_ip = packet.dst_ip
        current_time = time.time()

        # Step 1: ARP lookup
        if dst_ip not in self.arp_table:
            last_sent = self.arp_request_timestamps.get(dst_ip)
            if not last_sent or current_time - last_sent > 1:
                self.debug and print(f"{self.name}: Sending ARP request for {dst_ip}")
                self._send_arp_request(dst_ip, packet.src_ip, packet.src_mac, ttl, exclude_port)
                self.arp_request_timestamps[dst_ip] = current_time

            self.arp_queue[dst_ip].append((packet, ttl, current_time))
            return True

        # Step 2: ARP resolved — send packet
        dst_mac, port_id = self.arp_table[dst_ip]
        port_info = self._valid_port(port_id)
        if not port_info:
            self.debug and print(f"{self.name}: Invalid port {port_id} for {dst_ip}")
            return False

        port, neighbor = port_info
        packet.dst_mac = dst_mac
        self.debug and print(f"{self.name}: Forwarding packet to {dst_ip} via port {port.port_id}")

        # Step 3: Find neighbor's port that links back to this switch
        for nbr_port_id, nbr_port in neighbor.ports.items():
            if nbr_port.linked_node == self.name:
                return neighbor.receive_packet(packet, ttl - 1, in_port_id=nbr_port_id)

        self.debug and print(f"{self.name}: Could not find reverse port on {neighbor.name} for {dst_ip}")
        return False



    def _handle_indirect_route(self, packet: Packet, next_hop: str, ttl: int, exclude_port: int = None):
        current_time = time.time()

        # Step 1: Check ARP table
        if next_hop not in self.arp_table:
            # Step 2: Send ARP request if not recently sent
            last_sent = self.arp_request_timestamps.get(next_hop)
            if not last_sent or current_time - last_sent > 1:
                self.debug and print(f"{self.name}: Sending ARP request for next hop {next_hop}")
                self._send_arp_request(next_hop, packet.src_ip, packet.src_mac, ttl, exclude_port)
                self.arp_request_timestamps[next_hop] = current_time

            # Step 3: Enqueue packet
            self.arp_queue[next_hop].append((packet, ttl, current_time))
            return True

        # Step 4: If ARP entry exists, forward the packet
        next_mac, port_id = self.arp_table[next_hop]
        port_info = self._valid_port(port_id)
        if not port_info:
            self.debug and print(f"{self.name}: Invalid port {port_id} for next hop {next_hop}")
            return False

        port, neighbor = port_info
        packet.dst_mac = next_mac
        self.debug and print(f"{self.name}: Forwarding packet to {packet.dst_ip} via next hop {next_hop} on port {port.port_id}")
        return neighbor.receive_packet(packet, ttl - 1, in_port_id=port.port_id)


    def _is_local_ip(self, ip: str) -> bool:
        return any(
            ipaddress.ip_interface(iface.ip_address).ip == ipaddress.ip_address(ip)
            for iface in self.l3_interfaces.values()
        )

    # OSPF methods

    def _get_next_hop_ip_to(self, neighbor_name: str) -> Optional[str]:
        self.debug and print(f"[{self.name}] Looking for next hop IP to {neighbor_name}")
        self.debug and print(f"[{self.name}] My L3 interfaces: {[f'{i.name} -> {i.ip_address} (VLAN={i.vlan}, Port={i.port_id})' for i in self.l3_interfaces.values()]}")

        # Check port-based interfaces
        for iface in self.l3_interfaces.values():
            if iface.port_id is not None:
                port = self.ports[iface.port_id]
                if port.linked_node == neighbor_name:
                    neighbor = self.graph.nodes[neighbor_name]["object"]
                    for nbr_iface in neighbor.l3_interfaces.values():
                        if nbr_iface.port_id is not None:
                            nbr_port = neighbor.ports[nbr_iface.port_id]
                            if nbr_port.linked_node == self.name:
                                # print(f"[{self.name}] Found next-hop IP {nbr_iface.ip_address} from {neighbor_name}")
                                return str(ipaddress.ip_interface(nbr_iface.ip_address).ip)

        # Check VLAN-based interfaces
        for iface in self.l3_interfaces.values():
            if iface.vlan is not None:
                vlan = self.vlan_manager.vlans.get(iface.vlan)
                self.debug and print(f"[{self.name}] Checking VLAN {iface.vlan} for ports: {vlan.ports if vlan else 'None'}")
                if vlan:
                    for port_id in vlan.ports:
                        port = self.ports.get(port_id)
                        if port and port.linked_node == neighbor_name:
                            neighbor = self.graph.nodes[neighbor_name]["object"]
                            for nbr_iface in neighbor.l3_interfaces.values():
                                if nbr_iface.vlan == iface.vlan:
                                    # print(f"[{self.name}] Found next-hop IP {nbr_iface.ip_address} from {neighbor_name} on VLAN {iface.vlan}")
                                    return str(ipaddress.ip_interface(nbr_iface.ip_address).ip)

        self.debug and print(f"[{self.name}] Could not find next-hop IP to {neighbor_name}")
        return None

    def connect_port(self, port_id, neighbor_name):
        self.ports[port_id]['linked_node'] = neighbor_name
        self.graph.add_edge(self.name, neighbor_name)

    def exchange_ospf_lsa(self):
        my_lsa = self.ospf.lsdb[self.name]  # cache this once
        for port in self.ports.values():
            if port.status == 'up' and port.linked_node:
                neighbor = self.graph.nodes[port.linked_node]["object"]
                neighbor.receive_lsa(self.name, my_lsa)

    def receive_lsa(self, from_node: str, lsa: Dict[str, int]):
        updated = False
        if from_node not in self.ospf.lsdb or self.ospf.lsdb[from_node] != lsa:
            self.debug and print(f"[{self.name}] Received new LSA from {from_node}: {lsa}")
            self.ospf.lsdb[from_node] = lsa
            updated = True

        if updated:
            # Recalculate routes
            self.ospf.calculate_routes(self)
            self.redistribute_ospf_routes()

            # Flood this new LSA to neighbors (except the sender)
            for port in self.ports.values():
                if port.status == "up" and port.linked_node and port.linked_node != from_node:
                    neighbor = self.graph.nodes[port.linked_node]["object"]
                    self.debug and print(f"[{self.name}] Forwarding LSA of {from_node} to {port.linked_node}")
                    neighbor.receive_lsa(from_node, lsa)

    def redistribute_ospf_routes(self):
        for dst, (nexthop_ip, route_type) in self.ospf.get_ospf_routes().items():
            if dst not in self.routing_table:
                self.debug and print(f"[{self.name}] Installing OSPF route: {dst} → {nexthop_ip}")
                self.routing_table[dst] = (nexthop_ip, "ospf")

    def run_ospf(self):
        self.debug and print(f"[{self.name}] Starting OSPF process")

        # Step 1: Build a map of OSPF neighbors with their link cost
        neighbors = {}
        for port_id, port in self.ports.items():
            if port.status == 'up' and port.linked_node:
                cost = self.ospf.get_cost(port.speed_mbps)
                neighbors[port.linked_node] = cost
                self.debug and print(f"[{self.name}] Neighbor discovered: {port.linked_node} with cost {cost}")
        
        self.ospf.neighbors = neighbors  # ✅ Store neighbors

        # Step 2: Gather directly connected subnets
        self.ospf.connected_subnets = set()
        for iface_name, iface in self.l3_interfaces.items():
            try:
                network = str(ipaddress.ip_interface(iface.ip_address).network)
                self.ospf.connected_subnets.add(network)
                self.debug and print(f"[{self.name}] Connected subnet found: {network} (via {iface_name})")
            except ValueError as e:
                self.debug and print(f"[{self.name}] Invalid IP on interface {iface_name}: {iface.ip_address} ({e})")

        # Step 3: Update LSDB with this switch's neighbor map
        self.debug and print(f"[{self.name}] Updating LSDB with neighbors: {neighbors}")
        self.ospf.update_lsdb(neighbors)

        # Step 4: Exchange LSAs with neighbors
        self.debug and print(f"[{self.name}] Exchanging LSAs with neighbors...")
        self.exchange_ospf_lsa()

        # Step 5: Recalculate routes from updated LSDB
        self.debug and print(f"[{self.name}] Calculating OSPF routes from LSDB")
        self.ospf.calculate_routes(self)

        # Step 6: Install OSPF routes into main routing table
        self.debug and print(f"[{self.name}] Redistributing OSPF routes into routing table")
        self.redistribute_ospf_routes()

        self.debug and print(f"[{self.name}] OSPF process completed\n")   

    def show_ospf_routes(self):
        self.ospf.show_routing_table()    

    # Class Methods
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
            self.debug and print(f"Route {ip_cidr} removed.")
        else:
            self.debug and print(f"Route {ip_cidr} not found.")

    def create_vlan_interface(self, vlan_id: int, ip_with_prefix: str):
        if vlan_id not in self.vlan_manager.vlans:
            print(f"\n{self.name}: VLAN {vlan_id} does not exist. Please create it first.\n")
            return

        name = f"VLAN{vlan_id}"
        mac = generate_random_mac()
        iface = L3Interface(name=name, ip_address=ip_with_prefix, vlan=vlan_id, mac_address=mac)
        self.l3_interfaces[name] = iface

        # Add to routing table using the IP address, not the name
        network = ipaddress.ip_interface(ip_with_prefix).network
        ip = str(ipaddress.ip_interface(ip_with_prefix).ip)
        self.routing_table[str(network)] = (ip, "connected")

        # Self ARP
        self.arp_table[ip] = (mac, -1)
        self.mac_table[mac] = -1

    def assign_l3_interface_to_port(self, port_id: int, ip_with_prefix: str):
        name = f"Port{port_id}"
        self.ports[port_id].l3_enabled = True
        self.ports[port_id].ip_address = ip_with_prefix
        self.l3_interfaces[name] = L3Interface(name, ip_with_prefix, port_id=port_id)
        network = ipaddress.ip_interface(ip_with_prefix).network
        self.routing_table[str(network)] = (f"Port{port_id}", "connected")

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

    def show_ospf_neighbors(self):
        print(f"[OSPF Neighbors] for {self.name}")
        if not self.ospf.neighbors:
            print("  No neighbors discovered.")
            return

        print("{:<10} {:<6}".format("Neighbor", "Cost"))
        for neighbor, cost in self.ospf.neighbors.items():
            print(f"{neighbor:<10} {cost:<6}")

    def send_packet(self, packet: Packet, ttl: int = 10, exclude_port: int = None):
        self.debug and print(f"{self.name}: Sending packet to {packet.dst_ip} (exclude port={exclude_port})")

        # Step 1: Check TTL
        if ttl <= 0:
            self.debug and print(f"{self.name}: TTL expired for packet to {packet.dst_ip}")
            return False

        # Step 2: Route Lookup
        next_hop, route_type = self._lookup_route(packet.dst_ip)
        if not next_hop:
            self.debug and print(f"{self.name}: No route to {packet.dst_ip}")
            return False

        self.debug and print(f"{self.name}: Found next hop {next_hop} via {route_type} route")

        # Step 3: Forward Based on Route Type
        if route_type == "connected":
            return self._handle_connected_route(packet, ttl, exclude_port)
        elif route_type in ("static", "ospf"):
            return self._handle_indirect_route(packet, next_hop, ttl, exclude_port)
        else:
            self.debug and print(f"{self.name}: Unsupported route type {route_type}")
            return False

    
    def receive_packet(self, packet: Packet, ttl: int, in_port_id: int = None):
        self.debug and print(f"{self.name}: receive_packet called for {packet.dst_ip} (from {packet.src_ip}) on port {in_port_id}")        

        if ttl <= 1:
            self.debug and print(f"{self.name}: TTL expired for packet to {packet.dst_ip}")
            return False

        self._learn_arp(packet, in_port_id)

        # Is the destination one of our interfaces?
        dst_is_local = self._is_local_destination(packet.dst_ip)

        # ARP request
        if self._is_arp_request(packet):
            handled = self._handle_arp_request(packet, ttl, in_port_id)
            return handled or self._forward(packet, ttl, in_port_id)

        # ARP reply
        if self._is_arp_reply(packet):
            self._handle_arp_reply(packet, in_port_id)
            return True if dst_is_local else self._forward(packet, ttl, in_port_id)

        # ICMP ping
        if self._is_ping(packet):
            return self._handle_ping(packet, ttl) if dst_is_local else self._forward(packet, ttl, in_port_id)

        # ICMP reply
        if self._is_ping_reply(packet):
            return self._handle_ping_reply() if dst_is_local else self._forward(packet, ttl, in_port_id)

        # Catch-all for traffic to local
        if dst_is_local:
            self.debug and print(f"{self.name}: Packet for me ({packet.dst_ip}) - stopping here.")
            return True
        self.debug and print(f"{self.name}: Packet is not for me, forward it out except {in_port_id}")
        return self._forward(packet, ttl, in_port_id)


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
            sent = self.send_packet(packet, ttl=118)

            if not sent:
                writer.write("Ping error: failed to send packet.\r\n")
                continue

            # Wait for reply (simulate blocking ping)
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

        # Summary
        lost = count - success_count
        loss_percent = int((lost / count) * 100)

        writer.write(f"\r\nPing statistics for {dst_ip}:\r\n")
        writer.write(f"    Packets: Sent = {count}, Received = {success_count}, Lost = {lost} ({loss_percent}% loss),\r\n")

        if rtt_list:
            writer.write("Approximate round trip times in milli-seconds:\r\n")
            writer.write(f"    Minimum = {min(rtt_list)}ms, Maximum = {max(rtt_list)}ms, Average = {sum(rtt_list) // len(rtt_list)}ms\r\n")


