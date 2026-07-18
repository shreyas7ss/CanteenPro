import asyncio
import logging

import uvicorn

from app.bot import build_application, set_menu_button
from app.config import PORT
from app.server import app

logging.basicConfig(level=logging.INFO)


async def run_bot(application):
    await application.initialize()
    await set_menu_button(application)
    await application.start()
    await application.updater.start_polling()


async def main():
    application = build_application()
    config = uvicorn.Config(app, host="0.0.0.0", port=PORT, loop="asyncio")
    server = uvicorn.Server(config)
    await asyncio.gather(run_bot(application), server.serve())


if __name__ == "__main__":
    asyncio.run(main())
