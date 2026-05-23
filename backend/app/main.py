import asyncio

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.bot.runner import bot_runner
from app.config import settings
from app.routers import sessions, roster, players, inventory, pnl, venues

app = FastAPI(title="Badminton Session Manager", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router, prefix="/api/v1", tags=["sessions"])
app.include_router(roster.router, prefix="/api/v1", tags=["roster"])
app.include_router(players.router, prefix="/api/v1", tags=["players"])
app.include_router(inventory.router, prefix="/api/v1", tags=["inventory"])
app.include_router(pnl.router, prefix="/api/v1", tags=["pnl"])
app.include_router(venues.router, prefix="/api/v1", tags=["venues"])


@app.on_event("startup")
async def startup() -> None:
    bot_runner.build()
    asyncio.create_task(bot_runner.start_polling())


@app.on_event("shutdown")
async def shutdown() -> None:
    # The polling task is cancelled automatically when the event loop shuts down.
    pass


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
