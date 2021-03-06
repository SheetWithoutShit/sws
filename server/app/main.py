"""This module provides server app initialization."""

import os
import asyncio
import logging
import requests

from aiohttp.web import Application, run_app
from core.database.postgres import PoolManager as PGPoolManager
from core.database.redis import PoolManager as RedisPoolManager

from views.user import user_routes
from views.services import services_routes
from models.user import User
from models.spreadsheet import SpreadsheetAuth
from models.monobank import MonoBankAPI
from middlewares import check_auth, check_permission


LOG = logging.getLogger("")
LOG_FORMAT = "%(asctime)s - %(levelname)s: %(name)s: %(message)s"
ACCESS_LOG_FORMAT = "%a [VIEW: %r] [RESPONSE: %s (%bb)] [TIME: %Dms]"


def init_logging():
    """
    Initialize logging stream with debug level to console and
    create file logger with info level if permission to file allowed.
    """
    logging.basicConfig(format=LOG_FORMAT, level=logging.DEBUG)

    log_dir = os.environ.get("LOG_DIR")
    log_filepath = f'{log_dir}/server.log'
    if log_dir and os.path.isfile(log_filepath) and os.access(log_filepath, os.W_OK):
        formatter = logging.Formatter(LOG_FORMAT)
        file_handler = logging.FileHandler(log_filepath)
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logging.getLogger("").addHandler(file_handler)


async def init_clients(app):
    """
    Initialize aiohttp application with clients.
        * redis pool manager
        * postgres pool manager
        * user model
        * spreadsheet auth http client
        * monobank api http client
    """
    app["spreadsheet_auth"] = spreadsheet_auth = SpreadsheetAuth()
    app["monobank"] = monobank = MonoBankAPI()
    app["postgres"] = postgres = await PGPoolManager.create()
    app["redis"] = redis = await RedisPoolManager.create()

    app["user"] = User(postgres=postgres, redis=redis)
    LOG.debug("Clients has successfully initialized.")

    yield

    await asyncio.gather(
        spreadsheet_auth.close(),
        monobank.close(),
        postgres.close(),
        redis.close()
    )
    LOG.debug("Clients has successfully closed.")


async def init_constants(app):
    """Initialize aiohttp application with required constants."""
    app["constants"] = constants = {}

    response = requests.get("http://ngrok:4040/api/tunnels").json()
    _, http = response["tunnels"]
    ngrok_domain = http["public_url"]
    LOG.debug("NGROK forwarding to: %s", ngrok_domain)

    constants["NGROK_DOMAIN"] = os.environ["NGROK_DOMAIN"] = ngrok_domain
    constants["SECRET_KEY"] = os.environ["SECRET_KEY"]


def init_app():
    """Prepare aiohttp web server for further running."""
    app = Application()
    init_logging()

    app.add_routes(user_routes)
    app.add_routes(services_routes)

    app.cleanup_ctx.append(init_clients)
    app.on_startup.append(init_constants)

    app.middlewares.append(check_auth)
    app.middlewares.append(check_permission)

    return app


if __name__ == '__main__':
    host = os.environ.get("SERVER_HOST", "localhost")
    port = os.environ.get("SERVER_PORT", 5000)

    run_app(
        init_app(),
        host=host,
        port=port,
        access_log_format=ACCESS_LOG_FORMAT
    )
