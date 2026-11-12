from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import admin, orders, public
from app.core.config import get_settings
from app.core.validation import origin_of

settings = get_settings()
Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(_):
    settings.validate_for_runtime()  # не стартуем без токена, секрета и пароля админа
    yield


app = FastAPI(title="Luxury Store UZ", lifespan=lifespan,
              docs_url="/docs" if settings.debug else None,
              redoc_url=None, openapi_url="/openapi.json" if settings.debug else None)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
_mini = origin_of(settings.webapp_url)
if _mini and _mini not in origins:
    origins.append(_mini)
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                   allow_headers=["Authorization", "Content-Type"])

@app.middleware("http")
async def security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/api/admin"):
        resp.headers["Cache-Control"] = "no-store"  # ответы админки и персональные данные не кэшируются
    return resp


app.include_router(public.router)
app.include_router(orders.router)
app.include_router(admin.login_router)
app.include_router(admin.router)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")


@app.get("/api/health")
def health():
    return {"status": "ok"}
