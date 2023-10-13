from fastapi import FastAPI
from decouple import config
from fastapi.middleware.cors import CORSMiddleware

DB_URL = config('DB_URL', cast=str)
DB_NAME = config('DB_NAME', cast=str)

# define origins
origins = [
    "*"
]

# instantiate the app
app = FastAPI()

# add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)
