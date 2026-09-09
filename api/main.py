"""Application entry point."""

from fastapi import FastAPI

from api.routes import router


app = FastAPI(title="LLM Document Assistant")
app.include_router(router)