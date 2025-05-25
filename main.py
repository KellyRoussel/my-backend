from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from starlette.datastructures import State

from dependencies.auth_handler import auth_handler
from dependencies.auth_services.google_auth_service import GoogleAuthService
from endpoints.authentication import authentication_router
from endpoints.bobobidou import bobobidou_router
from endpoints.insta_poster import insta_poster_router
from endpoints.utils import utils_router


class MyBackendState(State):
    google_auth_service: GoogleAuthService
class MyBackendAPI(FastAPI):
    state: State


@asynccontextmanager
async def lifespan(application: MyBackendAPI):
    application.state.google_auth_service = GoogleAuthService()
    yield

app = MyBackendAPI(
    lifespan=lifespan,
    docs_url="/docs",
)

app.include_router(bobobidou_router, dependencies=[Depends(auth_handler)])
app.include_router(authentication_router)
app.include_router(insta_poster_router, dependencies=[Depends(auth_handler)])
app.include_router(utils_router, dependencies=[Depends(auth_handler)])

@app.get("/health")
def health():
    return {"status": "ok"}, 200