from fastapi import HTTPException, Body, APIRouter
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
from models import UserBase, LoginBase, RegisterUser, CustomJSONEncoder, LoginResponse, UserBaseWithId, UserBaseWithPass
from pydantic import BaseModel, Field
from bson import ObjectId
import json
from .users import has_permission_to_create
from authentication import AuthHandler
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

# instantiate the Auth Handler
auth_handler = AuthHandler()


@router.post("/register", response_description="Register user", response_model=UserBase)
async def register(
    request: Request, 
    newUser: RegisterUser = Body(...),
    # disabling security for simplification of creating new users for a new database.
    # userId=Depends(auth_handler.auth_wrapper)
) -> UserBaseWithId:
    """
    Register a new user.  Only a current user can create a new user.

    If userType not provided, the default is CLIENT_USER.

    The userType roles are listed in order of permissions:
    KURIOUS_SUPERUSER, KURIOUS_SALES, CLIENT_ADMIN, CLIENT_USER.
    Only a higher priority userType can create new roles of lower priority.
    E.g., a CLIENT_ADMIN can create a CLIENT_USER, but not another CLIENT_ADMIN,
    nor a KURIOUS_SALES, nor a KURIOUS_SUPERUSER.
    """
    # Note:  disabled checking status of current user to simplify the project
    #        so that users can easily be created without having any exising users
    #        in the collection
    # currentUser: UserBase = await request.app.mongodb["users"].find_one(
    #     {"_id": ObjectId(userId)})
    # currentUser = UserBase(**currentUser)
    # if currentUser.accountStatus != "ACTIVE":
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="Current user is not active and not authorized.")

    # hash the password before inserting it into MongoDB
    newUser.password = auth_handler.get_password_hash(newUser.password)
    newUser = newUser.dict()
    newUser['username'] = newUser['email']
    # UserBase instance will populate default values for fields such as dateJoined, lastLogin, etc.
    # with the fields in the proper format (datetimes as datetimes instead of strings), which
    # allows proper object insertion into database document fields.
    newUser = UserBaseWithPass(**newUser)

    # Check if the authenticated user has permission to create the new user
    # Disabled for simplicity to create new users
    # if not has_permission_to_create(currentUser.userType, newUser.userType):
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail=f"Current userType ({currentUser.userType.name}) has insufficient privileges to create the new user of userType {newUser.userType.name}.")

    # check existing user or email 409 Conflict:
    if (
        existing_email := await request.app.mongodb["users"].find_one(
            {"email": newUser.email}
        )
        is not None
    ):
        raise HTTPException(
            status_code=409, detail=f"User with email {newUser.email} already exists"
        )

    # check existing user or email 409 Conflict:
    if (
        existing_username := await request.app.mongodb["users"].find_one(
            {"username": newUser.username}
        )
        is not None
    ):
        raise HTTPException(
            status_code=409,
            detail=f"User with username {newUser.username} already exists",
        )

    user = await request.app.mongodb["users"].insert_one(newUser.dict())
    created_user = await request.app.mongodb["users"].find_one(
        {"_id": user.inserted_id},
        # Exclude the hashed password from the returned user object
        projection={"password": False}
    )
    
    response = JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=json.loads(json.dumps(created_user, cls=CustomJSONEncoder)))
    return response


# post user
@ router.post("/login", response_description="Login user")
async def login(request: Request, loginUser: LoginBase = Body(...)) -> LoginResponse:

    # find the user by email
    user = await request.app.mongodb["users"].find_one({"email": loginUser.email})

    # check password
    if (user is None) or (
        not auth_handler.verify_password(loginUser.password, user["password"])
    ):
        raise HTTPException(
            status_code=401, detail="Invalid email and/or password")

    # update lastLogin for the user
    await request.app.mongodb["users"].update_one(
        {"_id": user["_id"]},
        {"$set": {"lastLogin": datetime.now(timezone.utc)}}
    )

    # generate authentication token
    token = auth_handler.encode_token(str(user["_id"]))
    response = JSONResponse(
        content={"id": str(user["_id"]), "email": user["email"], "userType": user["userType"], "token": token})

    return response

# me route


@ router.get("/currentUser", response_description="Logged in user data")
async def currentUser(request: Request, userId=Depends(auth_handler.auth_wrapper)) -> UserBaseWithId:
    pipeline = [
        {"$match": {"_id": ObjectId(userId)}},
        {"$addFields": {"id": {"$toString": "$_id"}}},
        {"$project": {"_id": 0, "password": 0}},
    ]
    currentUser = await request.app.mongodb["users"].aggregate(pipeline).next()
    result = jsonable_encoder(UserBaseWithId(**currentUser))
    return JSONResponse(status_code=status.HTTP_200_OK, content=result)


class Password(BaseModel):
    password: str


@router.put("/resetPassword/{jwt}", response_description="Update User Password")
async def update_password(
    request: Request,
    jwt: str,
    password: Password = Body(..., example={'password': 'your-updated-password'})
):
    """
    Update User Password and Change Account Status to Active.

    This endpoint allows for the updating of a user's password and changing the account status
    to 'ACTIVE'. It decodes the JWT to get the user ID and then looks up the user in the MongoDB.
    If the user's account status is not 'ACTIVE' or 'PENDING', a 403 Forbidden error is raised.
    The password is then hashed, and the user's document in the MongoDB is updated with the new
    hashed password and the account status is set to 'ACTIVE'.

    Args:
        request (Request): FastAPI request object.
        jwt (str): The JSON Web Token (JWT) used to identify the user.
        password (Password): The new password for the user.

    Returns:
        dict: A message indicating that the password update was successful.

    Raises:
        HTTPException: If the user's account status is not 'ACTIVE' or 'PENDING', or if the JWT is invalid.

    Example:
        Input:
            jwt: 'example-jwt-token'
            password: {'password': 'your-updated-password'}
        Output:
            {"message": "User password updated; user accountStatus set to ACTIVE."}
    """
    # decode the JWT
    userId = auth_handler.decode_token(jwt)
    currentUser: UserBase = await request.app.mongodb["users"].find_one(
        {"_id": ObjectId(userId)})
    if currentUser is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Access token is valid, but the associated user with userId {userId} does not exist."
        )
    currentUser = UserBase(**currentUser)

    if currentUser.accountStatus not in ["ACTIVE", "PENDING"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Current user is not active or pending registration, and not authorized.")
    pd = auth_handler.get_password_hash(password.password)

    await request.app.mongodb["users"].update_one(
        {"_id": ObjectId(userId)},
        {
            "$set": {
                "password": pd,
                "accountStatus": "ACTIVE"
            }
        }
    )
    return JSONResponse(
        content={
            'success': True,
            'message': "User password updated; user accountStatus set to ACTIVE."
        },
        status_code=200)

