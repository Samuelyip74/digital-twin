
import asyncio
from networklab import NetworkLabCLI

if __name__ == "__main__":
    async def main():
        lab = NetworkLabCLI()
        print("\n\nStarting Digital Twin engine...")
        print("Loading initial Configuration...")
        await lab.load_config()  # ✅ Await the async config loader
        print("Configuration loaded.")
        print("Type 'show topology' or 'show graph' to see initial configuration.")
        print("Ready!")
        await lab.run()          # ✅ Await the CLI loop


    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down network lab.")

