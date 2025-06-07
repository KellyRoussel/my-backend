from datetime import datetime, timezone

import jwt
from fastapi import HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from starlette import status

from config import settings
from models.authentication import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

class AuthHandler:
    async def __call__(self, token: str = Depends(oauth2_scheme)):
        print("🤍 Authenticating")
        if token is None:
            print("🤍 Authenticating => token is None")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            print("🤍 Authenticating => token", token)
            payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
            print("🤍 Authenticating => payload", payload)
            email: str = payload.get("email")
            sub: str = payload.get("sub")
            exp: int = payload.get("exp")

            if sub is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication credentials",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # check expiration
            expiration_time = datetime.fromtimestamp(exp, tz=timezone.utc)
            now = datetime.now(timezone.utc)
            if expiration_time < now:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token expired",
                    headers={"WWW-Authenticate": "Bearer"},
                )


            return True

        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )


# Création d'une instance de la class d'authentification
auth_handler = AuthHandler()