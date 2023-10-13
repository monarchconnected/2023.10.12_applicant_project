from fastapi import APIRouter, Request, status, HTTPException, Depends
from models import UserBase, UserType, UserBaseWithId, Meta
from pydantic import BaseModel, Field
from bson import ObjectId

from authentication import AuthHandler

from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

# instantiate the Auth Handler
auth_handler = AuthHandler()

def has_permission_to_create(current_user_type: UserType, new_user_type: UserType) -> bool:
    priority = {
        UserType.KURIOUS_SUPERUSER: 4,
        UserType.KURIOUS_SALES: 3,
        UserType.CLIENT_ADMIN: 2,
        UserType.CLIENT_USER: 1
    }
    if priority[current_user_type] == 4:
        return True    # SUPERUSER can create any user type
    return priority[current_user_type] > priority[new_user_type]


class UsersResponse(BaseModel):
    meta: Meta
    data: list[UserBaseWithId]


@ router.get("/users", response_model=UsersResponse)
async def get_users(
    request: Request,
    userId=Depends(auth_handler.auth_wrapper),
    page: int = 1,
    pageSize: int = 20,
    firstName: str | None = None,
    lastName: str | None = None,
    companyName: str | None = None,
):
    currentUser: UserBase = await request.app.mongodb["users"].find_one(
        {"_id": ObjectId(userId)})
    currentUser = UserBase(**currentUser)
    if currentUser.accountStatus != "ACTIVE":
        # TODO:  put this into a function or class that is common for all functions
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Current user is not active and not authorized.")
    if not (currentUser.userType in [UserType.KURIOUS_SALES, UserType.KURIOUS_SUPERUSER]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Current user must be a Kurious employee to query users.")
    match_query = {}
    if firstName:
        match_query["firstName"] = {
            "$regex": f"{firstName}", "$options": "i"}
    if lastName:
        match_query["lastName"] = {"$regex": f"{lastName}", "$options": "i"}
    if companyName:
        match_query["companyName"] = {
            "$regex": f"{companyName}", "$options": "i"}
    pipeline = [
        {"$match": match_query},
        {"$addFields": {
            "id": {"$toString": "$_id"},
            "lastLogin": {
                "$concat": [
                    {
                        "$dateToString": {
                            "format": "%Y-%m-%dT%H:%M:%S.%L",
                            "date": "$lastLogin",
                            "timezone": "UTC",
                        }
                    },
                    "+00:00",
                ]
            },
            "dateJoined": {
                "$concat": [
                    {
                        "$dateToString": {
                            "format": "%Y-%m-%dT%H:%M:%S.%L",
                            "date": "$dateJoined",
                            "timezone": "UTC",
                        }
                    },
                    "+00:00",
                ]
            },
        }},
        {"$project": {"_id": 0, "password": 0}},
        {"$skip": (page - 1) * pageSize},
        {"$limit": pageSize},
    ]
    count_pipeline = [
        {"$match": match_query},
        {"$count": "totalCount"},
    ]

    try:
        users = await request.app.mongodb["users"].aggregate(pipeline).to_list(length=pageSize)
        count_result = await request.app.mongodb["users"].aggregate(count_pipeline).to_list(length=1)
        total_users = count_result[0]["totalCount"] if count_result else 0

        response = {
            "meta": {
                "page": page,
                "pageSize": pageSize,
                "totalCount": total_users,
                "count": len(users)
            },
            "data": users,
        }

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


