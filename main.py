import asyncio
import logging
from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import State

from config import settings
from dependencies.auth_handler import auth_handler
from dependencies.auth_services.google_auth_service import GoogleAuthService
from endpoints.authentication import authentication_router
from endpoints.bobobidou import bobobidou_router
from endpoints.insta_poster import insta_poster_router
from endpoints.utils import utils_router
from endpoints.investment import investment_router
from endpoints.portfolio import portfolio_router
from dependencies.portfolio.portfolio_agent import get_or_build_portfolio_agent


class MyBackendState(State):
    google_auth_service: GoogleAuthService
class MyBackendAPI(FastAPI):
    state: State


@asynccontextmanager
async def lifespan(application: MyBackendAPI):
    application.state.google_auth_service = GoogleAuthService()
    asyncio.create_task(get_or_build_portfolio_agent())
    yield

app = MyBackendAPI(
    lifespan=lifespan,
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.web_frontend_url,
        settings.portfolio_frontend_url,
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(bobobidou_router, dependencies=[Depends(auth_handler)])
app.include_router(authentication_router)
app.include_router(insta_poster_router, dependencies=[Depends(auth_handler)])
app.include_router(utils_router, dependencies=[Depends(auth_handler)])
app.include_router(investment_router, dependencies=[Depends(auth_handler)])
app.include_router(portfolio_router)
app.mount("/static", StaticFiles(directory="static"), name="static")
@app.get("/health")
def health():
    return {"status": "ok"}, 200