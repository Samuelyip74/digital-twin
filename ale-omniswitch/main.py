
import asyncio
from networklab import NetworkLabCLI

if __name__ == "__main__":
    async def main():
        lab = NetworkLabCLI()
        await lab.load_config()  # ✅ Await the async config loader
        await lab.run()          # ✅ Await the CLI loop

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down network lab.")

