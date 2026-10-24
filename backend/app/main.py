from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
import os

from .database import Base, engine
from .routers import auth, clinic, admin, public

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Delta Network - Federated Healthcare AI")

BASE_DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)  # git doesn't track empty dirs; don't crash on a fresh clone
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

app.include_router(auth.router)
app.include_router(clinic.router)
app.include_router(admin.router)
app.include_router(public.router)


@app.get("/health", tags=["ops"])
def health():
    """Liveness + readiness probe: used by the Docker HEALTHCHECK and by
    hosting platforms. Returns 503 if the database can't be reached, so an
    orchestrator can stop routing traffic to a broken instance."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"status": "unhealthy", "database": "down"}, status_code=503)
    return {"status": "ok", "database": "up"}


@app.get("/", response_class=HTMLResponse)
def root():
    return RedirectResponse(url="/login")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@app.get("/clinic/dashboard", response_class=HTMLResponse)
def clinic_dashboard_page(request: Request):
    return templates.TemplateResponse(request, "clinic_dashboard.html")


@app.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard_page(request: Request):
    return templates.TemplateResponse(request, "admin_dashboard.html")


@app.get("/admin/outbreak-monitor", response_class=HTMLResponse)
def outbreak_monitor_page(request: Request):
    return templates.TemplateResponse(request, "outbreak_monitor.html")


@app.get("/admin/drug-efficacy", response_class=HTMLResponse)
def drug_efficacy_page(request: Request):
    return templates.TemplateResponse(request, "drug_efficacy.html")


@app.get("/admin/stock-advisory", response_class=HTMLResponse)
def stock_advisory_page(request: Request):
    return templates.TemplateResponse(request, "stock_advisory.html")


@app.get("/public", response_class=HTMLResponse)
def public_dashboard_page(request: Request):
    return templates.TemplateResponse(request, "public_dashboard.html")
