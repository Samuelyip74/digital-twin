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


