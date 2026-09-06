from fastapi import APIRouter, HTTPException, status

from app.core.auth import create_token
from app.schemas.schemas import TokenRequest, TokenResponse, ViewerLoginRequest

router = APIRouter(prefix="/auth", tags=["auth"])

# Demo staff accounts for the CMS (role enforced server-side per route).
USERS = {
    "editor@peblo.tv": {"user_id": "editor@peblo.tv", "role": "editor"},
    "admin@peblo.tv": {"user_id": "admin@peblo.tv", "role": "admin"},
}

# Demo viewer accounts for the child-facing app. Passwords are demo-only; in
# production this endpoint would sit behind real identity (SSO/OAuth/child PINs).
VIEWERS = {
    "kids@peblo.tv": {"password": "peblo123", "name": "Kids"},
    "family@peblo.tv": {"password": "peblo123", "name": "Family"},
}


@router.post("/token", response_model=TokenResponse)
async def get_token(req: TokenRequest):
    """CMS token issuer: only known demo staff accounts, and only with their own role."""
    user = USERS.get(req.user_id)
    if not user or user["role"] != req.role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials for this role",
        )
    token = create_token(req.user_id, req.role)
    return TokenResponse(access_token=token, role=req.role)


@router.post("/viewer/token", response_model=TokenResponse)
async def get_viewer_token(req: ViewerLoginRequest):
    """Viewer login: email + password from the demo viewer accounts."""
    account = VIEWERS.get(req.email.strip().lower())
    if not account or account["password"] != req.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token = create_token(req.email.strip().lower(), "viewer")
    return TokenResponse(access_token=token, role="viewer")


@router.get("/me")
async def get_me():
    return {"message": "Use the token endpoint to get a token"}
