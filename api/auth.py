from datetime import datetime, timedelta, timezone
from typing import Annotated
import bcrypt
from fastapi import FastAPI, APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
import json
from passlib.context import CryptContext
from pydantic import BaseModel
from .dependencies import cache_db, logger


# to get a string like this run:
# openssl rand -hex 32
SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 5
PARTNER_LOGIN_KEY = "partner"


auth_router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    # dependencies=[Depends(get_current_active_user)],
    responses={404: {"description": "Not found"}},
)

fake_users_db = {
    "johndoe": {
        "api_login": "johndoe",
        "api_key": "$2b$12$NJIVwW8znzgKjXa6aq/bD.96nIgyLytvdZ8hYrwBj.MCdb/J7HOQ.",
        "partner_id": 8
    }
}


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    api_login: str | None = None


class User(BaseModel):
    api_login: str
    partner_id: int


class RedisUser(User):
    api_key: str


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def verify_password(plain_password, api_key):
    return pwd_context.verify(plain_password, api_key)


def get_password_hash(password):
    return pwd_context.hash(password)


# def get_user(db, api_login: str):
#     if api_login in db:
#         user_dict = db[api_login]
#         return UserInDB(**user_dict)


def get_user(api_login: str) -> RedisUser | bool:
    user_data = cache_db.get(f"{PARTNER_LOGIN_KEY}:{api_login}")
    user = json.loads(user_data) if user_data else None
    if user:
        return RedisUser(**user)
    return False


def authenticate_user(api_login: str, api_key: str):
    user = get_user(api_login)
    if not user:
        return False
    if not verify_password(api_key, user.api_key):
        return False
    return user


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        api_login: str = payload.get("sub")
        if api_login is None:
            raise credentials_exception
        token_data = TokenData(api_login=api_login)
    except JWTError:
        raise credentials_exception
    user = get_user(api_login=token_data.api_login)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
):
    if not current_user:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


@auth_router.post("/token")
async def auth_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()], ) -> Token:
    user = authenticate_user(api_login=form_data.username, api_key=form_data.password)
    logger.warning(user)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect api_login or api_key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.api_login}, expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer")


@auth_router.get("/testuser")
async def create_test_user():
    for un, dt in fake_users_db.items():
        cache_db.set(f"{PARTNER_LOGIN_KEY}:{un}", json.dumps(dt))
    return {}

# @auth_router.get("/users/me")
# async def read_users_me(
#     current_user: Annotated[User, Depends(get_current_active_user)],
# ):
#     return current_user
