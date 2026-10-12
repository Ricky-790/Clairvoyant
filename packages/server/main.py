import os

from api.routes.auth import router as auth_router
from api.routes.repos import router as repos_router
from api.routes.webhooks import router as webhooks_router
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

load_dotenv()

app = FastAPI()

app.add_middleware(
    SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "dev-secret")
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/ping")
def ping():
    return {"message": "pong"}


app.include_router(auth_router)
app.include_router(repos_router)
app.include_router(webhooks_router)
