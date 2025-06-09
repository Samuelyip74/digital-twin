import telnetlib3 # type: ignore
from omniswitch import OmniSwitchTelnetCLI

async def start_telnet_server(switch, host="localhost", port=8023):
    cli = OmniSwitchTelnetCLI(switch)
    await telnetlib3.create_server(host=host, port=port, shell=cli.interact, encoding="utf8")