
from typing import Dict, Optional, Tuple
from omniswitch import OmniSwitch
from osTelnetCLI import OmniSwitchTelnetCLI
import telnetlib3
import asyncio

import matplotlib.pyplot as plt
import networkx as nx
import ipaddress

class NetworkLabCLI:
    def __init__(self):
        self.switches: Dict[str, OmniSwitch] = {}
        self.telnet_ports = {}
        self.telnet_tasks = {}  
        self.base_port = 9000

    def add_node(self, name: str):
        if name in self.switches:
            print(f"Node {name} already exists.")
        else:
            sw = OmniSwitch(name)
            self.switches[name] = sw
            print(f"Added switch node: {name}")

    def link(self, sw1: str, port1: int, sw2: str, port2: int):
        if sw1 not in self.switches or sw2 not in self.switches:
            print("Both nodes must exist before linking.")
            return
        s1, s2 = self.switches[sw1], self.switches[sw2]
        s1.ports[port1].linked_node = sw2
        s1.ports[port1].status = "up"
        s2.ports[port2].linked_node = sw1
        s2.ports[port2].status = "up"

        # Add neighbor nodes to each other's graph with reference
        s1.graph.add_node(sw2, object=s2)
        s2.graph.add_node(sw1, object=s1)        
        print(f"Linked {sw1}:{port1} <--> {sw2}:{port2}")

    async def start_telnet(self, node: str):
        if node not in self.switches:
            print(f"Node {node} not found.")
            return

        if node in self.telnet_ports:
            print(f"Telnet already running on {node} (port {self.telnet_ports[node]})")
            return

        port = self.base_port + len(self.telnet_ports)
        self.telnet_ports[node] = port
        switch = self.switches[node]

        async def telnet_shell(reader, writer):
            cli = OmniSwitchTelnetCLI(switch)
            await cli.interact(reader, writer)

        async def launch_telnet():
            server = await telnetlib3.create_server(
                host='127.0.0.1',
                port=port,
                shell=telnet_shell,
                encoding='utf8'
            )
            print(f"[Telnet] Listening on port {port} for {node}")
            await server.serve_forever()

        print(f"Launching Telnet server for {node} on port {port}...")
        asyncio.create_task(launch_telnet())    

    def list_nodes(self):
        print("Nodes:")
        for name in self.switches:
            print(f" - {name}")

    def show_topology(self):
        print("Current Topology:")
        seen_links = set()

        for sw_name, switch in self.switches.items():
            for port_id, port in switch.ports.items():
                if port.linked_node:
                    # Create a consistent, undirected link key to avoid duplicates
                    link_key = tuple(sorted([(sw_name, port_id), (port.linked_node, switch.ports[port_id].port_id)]))
                    if link_key not in seen_links:
                        seen_links.add(link_key)
                        print(f"  {sw_name}:{port_id} <--> {port.linked_node}:{self.switches[port.linked_node].ports[port_id].port_id}")

    def draw_topology(self):
        G = nx.Graph()
        edge_labels = {}
        seen_links = set()

        # Add nodes
        for name in self.switches:
            G.add_node(name)

        # Add edges with port info and shared subnet
        for name, switch in self.switches.items():
            for port_id, port in switch.ports.items():
                if port.linked_node:
                    peer_name = port.linked_node
                    peer_switch = self.switches[peer_name]

                    # Find reciprocal port
                    peer_port = next((pid for pid, p in peer_switch.ports.items() if p.linked_node == name), None)
                    edge = tuple(sorted((name, peer_name)))

                    if edge not in seen_links:
                        seen_links.add(edge)

                        # Try to find shared subnet
                        subnets = []
                        for iface1 in switch.l3_interfaces.values():
                            for iface2 in peer_switch.l3_interfaces.values():
                                net1 = ipaddress.ip_interface(iface1.ip_address).network
                                net2 = ipaddress.ip_interface(iface2.ip_address).network
                                if net1 == net2:
                                    subnets.append(str(net1))

                        port_label = f"{name}:{port_id} ↔ {peer_name}:{peer_port}" if peer_port is not None else f"{name}:{port_id}"
                        label = port_label
                        if subnets:
                            label += f"\n{subnets[0]}"  # only show one

                        G.add_edge(*edge)
                        edge_labels[edge] = label

        # Draw graph
        pos = nx.spring_layout(G, seed=42)
        nx.draw(G, pos, with_labels=True, node_size=1600, node_color='lightyellow', font_weight='bold', edge_color='gray')
        nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=9, label_pos=0.5)

        plt.title("Network Topology with Port and Subnet Labels")
        plt.tight_layout()
        plt.show()


    async def run(self):
        print("Welcome to Network Lab CLI. Type 'help' for commands.")
        while True:
            try:
                cmd = await asyncio.to_thread(input, "lab> ")
            except (EOFError, KeyboardInterrupt):
                break

            cmd = cmd.strip()
            if cmd in {"exit", "quit"}:
                print("Exiting Lab CLI.")
                print("Shutting down network lab...")
                for node, task in self.telnet_tasks.items():
                    print(f" - Cancelling Telnet server for {node}")
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        print(f"   Telnet for {node} cancelled.")                
                break
            elif cmd == "help":
                print("""Available commands:
    add node <name>           - Add a new switch node
    link <sw1> <p1> <sw2> <p2> - Link two switch ports
    list                      - List all switch nodes
    start telnet <name>       - Start Telnet server for switch
    show topology             - Show the topology created
    exit                      - Exit CLI
    """)
            elif cmd.startswith("add node"):
                _, _, name = cmd.split()
                self.add_node(name)
            elif cmd.startswith("link"):
                parts = cmd.split()
                if len(parts) == 5:
                    self.link(parts[1], int(parts[2]), parts[3], int(parts[4]))
                else:
                    print("Usage: link <sw1> <port1> <sw2> <port2>")
            elif cmd.startswith("list"):
                self.list_nodes()
            elif cmd.startswith("start telnet"):
                _, _, name = cmd.split()
                await self.start_telnet(name)
            elif cmd == "show topology":
                self.show_topology()     
            elif cmd == "show graph":
                self.draw_topology()                           
            else:
                print(f"Unknown command: {cmd}")


    # async def load_config(self):
    #     print("[Lab] Loading predefined configuration...")

    #     # Step 1: Add nodes
    #     self.add_node("sw1")
    #     self.add_node("sw2")
    #     self.add_node("sw3")

    #     # Step 2: Link sw1:1 <--> sw2:1
    #     self.link("sw1", 1, "sw2", 1)
    #     self.link("sw2", 2, "sw3", 1)

    #     # Step 3: Apply VLAN and IP config
    #     sw1 = self.switches["sw1"]
    #     sw2 = self.switches["sw2"]
    #     sw3 = self.switches["sw3"]

    #     sw1.vlan_manager.create_vlan(1)
    #     sw1.create_vlan_interface(1, "10.1.1.1/24")

    #     sw2.vlan_manager.create_vlan(1)
    #     sw2.create_vlan_interface(1, "10.1.1.2/24")

    #     sw3.vlan_manager.create_vlan(1)
    #     sw3.create_vlan_interface(1, "10.1.1.3/24")        
    #     await self.start_telnet("sw1")
    #     await self.start_telnet("sw2")
    #     await self.start_telnet("sw3")
    #     print("[Lab] Configuration loaded.")

    async def load_config(self):
        print("[Lab] Loading predefined configuration...")

        # Step 1: Add nodes
        self.add_node("sw1")
        self.add_node("sw2")
        self.add_node("sw3")

        # Step 2: Link sw1:1 <--> sw2:1
        self.link("sw1", 1, "sw2", 1)
        self.link("sw2", 2, "sw3", 1)

        # Step 3: Apply VLAN and IP config
        sw1 = self.switches["sw1"]
        sw2 = self.switches["sw2"]
        sw3 = self.switches["sw3"]

        sw1.vlan_manager.create_vlan(1)
        sw1.create_vlan_interface(1, "10.1.1.1/24")

        sw2.vlan_manager.create_vlan(1)
        sw2.create_vlan_interface(1, "10.1.1.2/24")
        sw2.vlan_manager.create_vlan(2)
        sw2.create_vlan_interface(2, "10.1.2.2/24")        

        sw3.vlan_manager.create_vlan(2)
        sw3.create_vlan_interface(2, "10.1.2.3/24")        
        await self.start_telnet("sw1")
        await self.start_telnet("sw2")
        await self.start_telnet("sw3")
        print("[Lab] Configuration loaded.")    

if __name__ == "__main__":
    async def main():
        lab = NetworkLabCLI()
        await lab.load_config()  # ✅ Await the async config loader
        await lab.run()          # ✅ Await the CLI loop

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down network lab.")

