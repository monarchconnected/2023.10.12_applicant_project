import jwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os


load_dotenv()
JWT_SECRET = os.getenv('JWT_SECRET')
JWT_EXPIRE_MINUTES = int(os.getenv('JWT_EXPIRE_MINUTES'))


class AuthHandler:

    security = HTTPBearer()
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    secret = JWT_SECRET

    def get_password_hash(self, password):
        return self.pwd_context.hash(password)

    def verify_password(self, plain_password, hashed_password):
        return self.pwd_context.verify(plain_password, hashed_password)

    def encode_token(self, user_id, jwt_expire_minutes=JWT_EXPIRE_MINUTES):
        payload = {
            "exp": datetime.utcnow() + timedelta(days=0, minutes=jwt_expire_minutes),
            "iat": datetime.utcnow(),
            "sub": user_id,
        }
        return jwt.encode(payload, self.secret, algorithm="HS256")

    def decode_token(self, token):
        try:
            payload = jwt.decode(token, self.secret, algorithms=["HS256"])
            return payload["sub"]
        except jwt.ExpiredSignatureError:
            print('Expired Token.')
            raise HTTPException(
                status_code=401, detail="Signature has expired")
        except jwt.InvalidTokenError as e:
            print('Invalid Token.')
            raise HTTPException(status_code=401, detail="Invalid token")

    def auth_wrapper(self, auth: HTTPAuthorizationCredentials = Security(security)):
        return self.decode_token(auth.credentials)
