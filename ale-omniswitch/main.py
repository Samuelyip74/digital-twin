
from typing import Dict, Optional, Tuple
from omniswitch import OmniSwitch
from osTelnetCLI import OmniSwitchTelnetCLI
import telnetlib3
import asyncio


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
            else:
                print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    try:
        lab = NetworkLabCLI()
        asyncio.run(lab.run())
    except KeyboardInterrupt:
        print("\nShutting down network lab.")

