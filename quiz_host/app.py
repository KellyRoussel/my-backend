"""Standalone Quiz Host app: only the quiz router and its static files.

The full backend (main.py) also needs a database and the other features' keys;
this entry point runs the quiz alone:

    uvicorn quiz_host.app:app --reload
"""
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from endpoints.quiz import quiz_router

app = FastAPI(title="Quiz Host")
app.include_router(quiz_router)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/quiz")
