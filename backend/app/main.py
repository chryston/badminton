import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.bot.runner import bot_runner
from app.config import settings
from app.routers import sessions, roster, players, inventory, pnl, venues, court_slots


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    bot_runner.build()
    polling_task = asyncio.create_task(bot_runner.start_polling())
    yield
    # shutdown
    polling_task.cancel()
    try:
        await polling_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Badminton API", lifespan=lifespan)

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    detail = str(exc)
    status_code = 404 if "not found" in detail.lower() else 422
    return JSONResponse(status_code=status_code, content={"detail": detail})


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
app.include_router(court_slots.router, prefix="/api/v1", tags=["court-slots"])


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
