"""FastAPI backend for the Vessel DMS application.

It provides the document management endpoints and a lightweight Microsoft
Entra authentication bridge that stores the signed-in user's profile in the
configured database when available, or otherwise keeps it in memory.
"""
import re

# pyrefly: ignore [missing-import]
from fastapi import FastAPI, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
# pyrefly: ignore [missing-import]
from sqlalchemy.exc import OperationalError

from .auth import AuthError, authenticate_user, check_email_in_tenant, store_user_profile
from .db.base import Base, engine, SessionLocal
from .db.models import User
"""Stub FastAPI for the SharePoint Embedded DMS — Phase A (UI-first).

Serves realistic, correctly-shaped data from an in-memory store so the React UI
can be built against the final endpoint contracts. No Graph/OCR/DB yet.
"""
import re

from fastapi import FastAPI, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .store import DuplicateFile, store

app = FastAPI(title="Vessel DMS (stub)", version="0.1.0")

if engine is not None:
    try:
        Base.metadata.create_all(bind=engine)
    except OperationalError:
        pass

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class VesselIn(BaseModel):
    name: str
    imo: str | None = None


class TokenLogin(BaseModel):
    access_token: str | None = None
    email: str | None = None
    password: str | None = None
    tenant_id: str | None = None


class LogoutPayload(BaseModel):
    email: str | None = None


class CheckEmailPayload(BaseModel):
    email: str


@app.get("/api/vessels")
def list_vessels():
    return [
        {"id": v["id"], "name": v["name"], "imo": v.get("imo")}
        for v in store.vessels
    ]


@app.post("/api/vessels", status_code=201)
def create_vessel(payload: VesselIn):
    name = payload.name.strip()
    imo = (payload.imo or "").strip()
    if not name:
        raise HTTPException(400, "Vessel name is required")
    if imo and not re.fullmatch(r"\d{7}", imo):
        raise HTTPException(400, "IMO number must be exactly 7 digits")
    if any(v["name"].lower() == name.lower() for v in store.vessels):
        raise HTTPException(409, "A vessel with that name already exists")
    if imo and any(v.get("imo") == imo for v in store.vessels):
        raise HTTPException(409, "A vessel with that IMO number already exists")
    return store.add_vessel(name, imo or None)


@app.get("/api/tree")
def get_tree():
    return store.tree()


@app.get("/api/folders/{folder_id}/children")
def get_children(folder_id: str):
    if store.get_node(folder_id) is None:
        raise HTTPException(404, "Folder not found")
    return store.children(folder_id)


@app.post("/api/folders/{folder_id}/upload")
async def upload(folder_id: str, file: UploadFile):
    node = store.get_node(folder_id)
    if node is None:
        raise HTTPException(404, "Folder not found")
    if not node["upload"] or node["month_driven"]:
        raise HTTPException(400, "This folder does not accept direct uploads")
    data = await file.read()
    try:
        return store.upload(folder_id, file.filename, data, file.content_type)
    except DuplicateFile:
        raise HTTPException(409, f"'{file.filename}' already exists in this folder")


@app.post("/api/folders/{folder_id}/month-upload")
async def month_upload(folder_id: str, file: UploadFile, category: str = Form(None)):
    node = store.get_node(folder_id)
    if node is None:
        raise HTTPException(404, "Folder not found")
    if not node["month_driven"]:
        raise HTTPException(400, "This folder is not a month-driven folder")
    data = await file.read()
    try:
        return store.month_upload(
            folder_id, file.filename, category, data, file.content_type
        )
    except DuplicateFile:
        raise HTTPException(
            409, f"'{file.filename}' already exists in the target month folder"
        )


@app.get("/api/files/{file_id}/content")
def file_content(file_id: str):
    result = store.get_file(file_id)
    if result is None:
        raise HTTPException(404, "File not found")
    content, content_type, name = result
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{name}"'},
    )


@app.delete("/api/files/{file_id}", status_code=204)
def delete_file(file_id: str):
    if not store.delete_file(file_id):
        raise HTTPException(404, "File not found")
    return Response(status_code=204)


@app.get("/api/search")
def search(q: str = ""):
    return store.search(q)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


@app.post("/api/auth/check-email")
def check_email(payload: CheckEmailPayload):
    """
    Pre-flight check called by the login page BEFORE the MSAL redirect.
    Returns 200 if the email is a recognised tenant member or B2B guest,
    403 otherwise — so unauthorised users never reach the Microsoft OTP screen.
    """
    email = payload.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "A valid email address is required")
    if not check_email_in_tenant(email):
        raise HTTPException(
            403,
            "This email address is not authorised to access this application. "
            "Contact your administrator to request access.",
        )
    return {"status": "ok"}


@app.post("/api/auth/login")
def login(payload: TokenLogin):
    if payload.access_token:
        try:
            profile = authenticate_user(payload.access_token, tenant_id=payload.tenant_id)
        except AuthError as exc:
            raise HTTPException(401, str(exc)) from exc
        return profile

    if not payload.email or not payload.password:
        raise HTTPException(400, "Email and password are required")

    profile = {
        "id": f"email:{payload.email}",
        "displayName": payload.email.split("@", 1)[0],
        "mail": payload.email,
        "userPrincipalName": payload.email,
    }
    return store_user_profile(profile, tenant_id=payload.tenant_id)


@app.post("/api/auth/logout")
def logout(payload: LogoutPayload):
    if payload.email and SessionLocal is not None:
        try:
            db = SessionLocal()
            user = db.query(User).filter(User.email == payload.email).first()
            if user:
                user.is_active = False
                db.commit()
                db.refresh(user)
        except Exception as e:
            print("Database error during logout:", e)
        finally:
            db.close()
    return {"status": "success"}


@app.get("/api/health")
def health():
    return {"status": "ok"}
