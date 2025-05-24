import jwt
from fastapi import HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from starlette import status

from config import settings
from models.authentication import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

class AuthHandler:
    async def __call__(self, token: str = Depends(oauth2_scheme)):
        if token is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
            print(payload)
            email: str = payload.get("email")
            sub: str = payload.get("sub")
            name: str = payload.get("name")
            picture: str = payload.get("picture")

            if sub is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication credentials",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            user = User(
                email=email,
                id=sub,
                name=name,
                picture=picture
            )
            return user

        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )


# Création d'une instance de la class d'authentification
auth_handler = AuthHandler()