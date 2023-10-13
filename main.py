from config import app, DB_URL, DB_NAME
from motor.motor_asyncio import AsyncIOMotorClient

from routers.users import router as users_router
from routers.auth import router as auth_router
from routers.companies import router as companies_router


@app.on_event("startup")
async def startup_db_client():
    app.mongodb_client = AsyncIOMotorClient(DB_URL)
    app.mongodb = app.mongodb_client[DB_NAME]


@app.on_event("shutdown")
async def shutdown_db_client():
    app.mongodb_client.close()


app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(users_router, prefix="", tags=["users"])
app.include_router(companies_router, prefix="", tags=["companies"])
