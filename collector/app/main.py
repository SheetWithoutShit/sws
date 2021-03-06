"""This module provides app initialization."""

import os
import asyncio
import logging

from aiohttp.web import Application, run_app
from core.database.postgres import PoolManager as PGPoolManager
from core.database.redis import PoolManager as RedisPoolManager
from core.telegram import TelegramBot

from views import routes
from models.user import User
from models.transaction import Transaction


LOG = logging.getLogger("")
LOG_FORMAT = "%(asctime)s - %(levelname)s: %(name)s: %(message)s"
ACCESS_LOG_FORMAT = "%a [VIEW: %r] [RESPONSE: %s (%bb)] [TIME: %Dms]"
SELECT_MCC_CODES = """
    SELECT code, category FROM "MCC";
"""


def init_logging():
    """
    Initialize logging stream with debug level to console and
    create file logger with info level if permission to file allowed.
    """
    logging.basicConfig(format=LOG_FORMAT, level=logging.DEBUG)

    log_dir = os.environ.get("LOG_DIR")
    log_filepath = f'{log_dir}/collector.log'
    if log_dir and os.path.isfile(log_filepath) and os.access(log_filepath, os.W_OK):
        formatter = logging.Formatter(LOG_FORMAT)
        file_handler = logging.FileHandler(log_filepath)
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logging.getLogger("").addHandler(file_handler)


async def prepare_data(app):
    """
    Prepare required data for correct application work.
        * Store mcc codes retrieved from postgres to redis.
    """
    postgres, redis = app["postgres"], app["redis"]
    codes = {x["code"]: x["category"] for x in await postgres.fetch(SELECT_MCC_CODES)}
    await redis.dump("mcc", codes)
    LOG.debug("Data was successfully prepared.")

    yield

    await redis.remove("mcc")
    LOG.debug("Data was successfully cleaned.")


async def init_clients(app):
    """
    Initialize aiohttp application with clients.
        * telegram bot
        * redis pool manager
        * postgres pool manager
        * transaction model
    """
    app["bot"] = bot = TelegramBot()
    app["postgres"] = postgres = await PGPoolManager.create()
    app["redis"] = redis = await RedisPoolManager.create()

    app["transaction"] = Transaction(postgres=postgres, redis=redis)
    app["user"] = User(postgres=postgres, redis=redis)
    LOG.debug("Clients has successfully initialized.")

    yield

    await asyncio.gather(
        postgres.close(),
        redis.close(),
        bot.close()
    )
    LOG.debug("Clients has successfully closed.")


def init_app():
    """Prepare aiohttp web server for further running."""
    app = Application()

    init_logging()

    app.add_routes(routes)

    app.cleanup_ctx.append(init_clients)
    app.cleanup_ctx.append(prepare_data)

    return app


if __name__ == '__main__':
    host = os.environ.get("COLLECTOR_HOST", "localhost")
    port = os.environ.get("COLLECTOR_PORT", 5010)

    run_app(
        init_app(),
        host=host,
        port=port,
        access_log_format=ACCESS_LOG_FORMAT
    )
