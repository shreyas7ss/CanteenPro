import asyncio
import logging

import uvicorn

from app.config import PORT
from app.server import app

logging.basicConfig(level=logging.INFO)


async def main():
    config = uvicorn.Config(app, host="0.0.0.0", port=PORT, loop="asyncio")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
