from typing import Optional

from pydantic import BaseModel


class TokenData(BaseModel):
    email: Optional[str] = None
    sub: Optional[str] = None
    name: Optional[str] = None
    picture: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str


class User(BaseModel):
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None
    id: str