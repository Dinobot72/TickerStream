from fastapi import APIRouter, HTTPException, Depends, Response, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, COOKIE_NAME
from app.core.database import get_db_connection

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- Models ---
class User(BaseModel):
    username: str
    password: str
    first_name: str
    last_name: str

class LoginCredentials(BaseModel):
    username: str
    password: str

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class CookieBearer(HTTPBearer):
    async def __call__(self, request: Request) -> Optional[HTTPAuthorizationCredentials]:
        token = request.cookies.get(COOKIE_NAME)
        if token:
            return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        
        return await super().__call__(request)
    
cookie_bearer = CookieBearer(auto_error=False)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def set_auth_cookie(response: Response, token: str):
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True, 
        samesite="none",
        domain=".ticker-stream.com",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/"
    )

async def get_current_user(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(cookie_bearer)):
    token = request.cookies.get(COOKIE_NAME)
    if not token and credentials:
        token = credentials.credentials

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        user_id: int = payload.get("id")
        if username is None or user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"username": username, "user_id": user_id}
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalid")

# --- Routes ---
@router.post("/api/register")
def register_user(user: User):
    hashed_pass = get_password_hash(user.password)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, password, first_name, last_name) VALUES (?, ?, ?, ?)",
                       (user.username, hashed_pass, user.first_name, user.last_name))
        user_id = cursor.lastrowid
        cursor.execute("INSERT INTO portfolios (user_id, balance) VALUES (?, ?)", (user_id, 0.00))
        conn.commit()
    except Exception:
        raise HTTPException(status_code=400, detail="Username already exists")
    finally:
        conn.close()
    return {"message": "User registered successfully"}

@router.post("/api/login")
def login(response: Response, credentials: LoginCredentials):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, password FROM users WHERE username = ?", (credentials.username,))
    user = cursor.fetchone()
    conn.close()

    if not user or not verify_password(credentials.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token(data={"sub": credentials.username, "id": user["user_id"]})
    set_auth_cookie(response, access_token)
    return {"message": "Login successful", "access_token": access_token, "user_id": user["user_id"]}

@router.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"message": "Logged out"}

@router.get("/api/auth/status")
def auth_status(current_user: dict = Depends(get_current_user)):
    return {"authenticated": True, "user": current_user}

@router.post("/api/user/{user_id}/change-password")
def change_password(user_id: int, data: PasswordChange, current_user: dict = Depends(get_current_user)):
    if current_user["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    
    if not user or not verify_password(data.current_password, user["password"]):
        conn.close()
        raise HTTPException(status_code=400, detail="Incorrect password")
        
    new_hash = get_password_hash(data.new_password)
    cursor.execute("UPDATE users SET password = ? WHERE user_id = ?", (new_hash, user_id))
    conn.commit()
    conn.close()
    return {"message": "Password updated"}