import asyncio
import telnetlib3
import subprocess
import platform
from omniswitch import OmniSwitch
from osTelnetCLI import OmniSwitchTelnetCLI


# Telnet Shell handler
async def shell(reader, writer):
    switch = OmniSwitch("sw1")
    cli = OmniSwitchTelnetCLI(switch)
    await cli.interact(reader, writer)


async def start_telnet_server(port=8023):
    server = await telnetlib3.create_server(
        host='127.0.0.1',
        port=port,
        shell=shell,
        encoding='utf8'
    )
    print(f"[Telnet] Server running on port {port}")
    return server


def launch_telnet_blocking(port=8023):
    if platform.system() == "Windows":
        print("[Telnet] Launching telnet client...")
        # Blocks until the telnet session exits
        subprocess.run(['cmd', '/c', f'telnet 127.0.0.1 {port}'])
    else:
        subprocess.run(['telnet', '127.0.0.1', str(port)])


async def main():
    port = 8023
    server = await start_telnet_server(port)

    # Launch telnet client in blocking call (runs until user closes session)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, launch_telnet_blocking)

    print("[Telnet] Telnet session closed. Shutting down server.")
    server.close()
    await server.wait_closed()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrupted. Cleaning up...")
