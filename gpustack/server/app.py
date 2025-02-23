from contextlib import asynccontextmanager
from pathlib import Path
import aiohttp
from fastapi import FastAPI
from fastapi_cdn_host import patch_docs

from gpustack import __version__
from gpustack.api import exceptions, middlewares
from gpustack.routes import ui
from gpustack.routes.routes import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = aiohttp.ClientSession()
    yield
    await app.state.http_client.close()


app = FastAPI(
    title="GPUStack",
    lifespan=lifespan,
    response_model_exclude_unset=True,
    version=__version__,
)
patch_docs(app, Path(__file__).parents[1] / "ui" / "static")
app.add_middleware(middlewares.RequestTimeMiddleware)
app.add_middleware(middlewares.ModelUsageMiddleware)
app.add_middleware(middlewares.RefreshTokenMiddleware)
app.include_router(api_router)
ui.register(app)
exceptions.register_handlers(app)
