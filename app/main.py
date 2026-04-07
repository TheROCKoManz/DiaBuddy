from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from authlib.integrations.starlette_client import OAuth
from pydantic import BaseModel

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from app.config import get_settings
from app.auth import create_token, verify_token
from app.agent import root_agent

settings = get_settings()

app = FastAPI(title="DiaBuddy API", docs_url=None, redoc_url=None)

# SessionMiddleware is needed for authlib to store OAuth state between redirect and callback.
# State is stored in a signed browser cookie — no server-side session data is persisted.
app.add_middleware(SessionMiddleware, secret_key=settings.jwt_secret, max_age=600)

oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.google_oauth_client_id,
    client_secret=settings.google_oauth_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.get("/auth/google")
async def login(request: Request):
    redirect_uri = f"{settings.app_base_url}/auth/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth/callback")
async def auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth flow failed")

    user_info = token.get("userinfo")
    if not user_info:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not retrieve user info from Google")

    email = user_info.get("email", "").lower()
    if email not in settings.allowed_email_list:
        return HTMLResponse(
            content="<h2>Access Denied</h2><p>Your Google account is not authorized to use this app.</p>",
            status_code=403,
        )

    jwt_token = create_token(email)
    # Redirect to Streamlit frontend (served at / by nginx) with the token in query params
    return RedirectResponse(url=f"/?token={jwt_token}")


# ---------------------------------------------------------------------------
# Protected API routes
# ---------------------------------------------------------------------------

class InsulinRequest(BaseModel):
    meal_description: str
    blood_sugar: float


@app.get("/api/me")
async def me(email: str = Depends(verify_token)):
    """Returns the authenticated user's email. Used by the frontend to validate stored tokens."""
    return {"email": email}


@app.post("/api/check-insulin")
async def check_insulin(body: InsulinRequest, email: str = Depends(verify_token)):
    """
    Runs the DiaBuddy ADK pipeline for the given food and blood sugar level.
    Creates a fresh in-memory session per request — no data is persisted.
    """
    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name="diabuddy", user_id="patient")
    runner = Runner(agent=root_agent, app_name="diabuddy", session_service=session_service)

    user_message = (
        f"I am going to eat: {body.meal_description}. "
        f"My pre-meal blood sugar is {body.blood_sugar} mg/dl."
    )
    message = Content(role="user", parts=[Part(text=user_message)])

    recommendation = None
    async for event in runner.run_async(user_id="patient", session_id=session.id, new_message=message):
        if event.is_final_response() and event.content and event.content.parts:
            if event.author == "insulin_agent":
                recommendation = event.content.parts[0].text
                break

    if not recommendation:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Agent failed to produce a dosage recommendation")

    return {
        "recommendation": recommendation,
        "meal_description": body.meal_description,
        "blood_sugar": body.blood_sugar,
    }