from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import init_db
from app.utils.logger import get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("lifespan: starting Research Validator backend")

    pool = await init_db(settings.database_url)
    app.state.pool = pool
    log.info("lifespan: PostgreSQL pool ready")

    yield

    await pool.close()
    log.info("lifespan: pool closed")


app = FastAPI(
    title="Research Validator API",
    description="Multi-agent arXiv paper evaluation powered by LangGraph",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.routes import router  # noqa: E402
app.include_router(router)


@app.get("/")
async def root():
    return {"service": "Research Validator API", "version": "0.1.0", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=settings.debug)
