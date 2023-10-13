from fastapi import APIRouter, Request, Body, status, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from datetime import datetime, timezone, timedelta
from models import NewCompany, Company, UserBase, UserType, CustomJSONEncoder, UserBaseWithId
from pydantic import BaseModel, Field, EmailStr
from bson import ObjectId
import json
from typing import List
from enum import Enum

from authentication import AuthHandler

router = APIRouter()

# instantiate the Auth Handler
auth_handler = AuthHandler()


class CompanyInDB(Company):
    email: EmailStr | None = Field(None,
                                   description="Email address of company admin", example='bill.smith@gmail.com')
    users: list[UserBaseWithId] = Field(
        ...,
        description="List of the users associated with the company",
        example=[
            UserBaseWithId(
                id="5f456791b849a8cadda92d02",
                username="jane.doe@gmail.com",
                email="jane.doe@egmail.com",
                firstName="Jane",
                lastName="Doe",
                companyName="XYZ Trucking",
                userType="CLIENT_USER",
                accountStatus="ACTIVE",
                lastLogin=datetime.now(timezone.utc) - timedelta(minutes=51),
                dateJoined=datetime.now(timezone.utc) - timedelta(weeks=42),
            ),
            UserBaseWithId(
                id="5f456791b849a8cadda92d01",
                username="john.doe@gmail.com",
                email="john.doe@egmail.com",
                firstName="John",
                lastName="Doe",
                companyName="XYZ Trucking",
                userType="CLIENT_USER",
                accountStatus="ACTIVE",
                lastLogin=datetime.now(timezone.utc) - timedelta(minutes=88),
                dateJoined=datetime.now(timezone.utc) - timedelta(weeks=20),
            )
        ]
    )


class UserInDB(UserBase):
    id: str


async def get_and_check_user(userId: str, request: Request) -> UserBase:
    currentUser = await request.app.mongodb["users"].find_one(
        {"_id": ObjectId(userId)})
    if currentUser is None or currentUser.get("accountStatus") != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Current user is not active and not authorized.")
    return UserBase(**currentUser)



def check_user_permissions(
    currentUser: UserBase,
    allowed_user_types: List[UserType] = [UserType.KURIOUS_SUPERUSER, UserType.KURIOUS_SALES]
) -> bool:
   # TODO: add check to see if currentUser accountStatus is "ACTIVE".  
   # This function should return 403 forbidden for accountStatus other than "ACTIVE"
    if currentUser.userType not in allowed_user_types:
        allowed_types_str = ', '.join([user_type.value for user_type in allowed_user_types])
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only {allowed_types_str} userTypes can create new company accounts. You have userType {currentUser.userType.value}")
    return True


async def get_company_admin(email: str, request: Request) -> dict:
    company_admin = await request.app.mongodb["users"].find_one({"email": email})
    if company_admin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"A user with email {email} does not exist. User with this email must be registered first.")
    return company_admin


@router.post("/companies", response_model=CompanyInDB)
async def create_company(request: Request, newCompany: NewCompany, userId=Depends(auth_handler.auth_wrapper)):
    '''Add new company.  admin for this company must already exist in the users database.'''
    currentUser: UserBase = await get_and_check_user(userId, request)
    check_user_permissions(currentUser, allowed_user_types=[UserType.KURIOUS_SUPERUSER, UserType.KURIOUS_SALES])
    company_admin = await get_company_admin(newCompany.email, request)

    company = Company(
        companyName=newCompany.companyName,
        tokenUsage=0,
        tokenAllotment=newCompany.tokenAllotment,
        isActive=True,
        adminId=str(company_admin["_id"]),
        lastUpdated=datetime.now(timezone.utc),
        dateCreated=datetime.now(timezone.utc)
    )
    result = await request.app.mongodb["companies"].insert_one(company.dict(exclude_unset=True))
    pipeline = [
        {"$match": {"_id": result.inserted_id}},
        {"$addFields": {"companyId": {"$toString": "$_id"}}},
        {"$project": {"_id": 0}},
    ]
    created_company = await request.app.mongodb["companies"].aggregate(pipeline).next()
    created_company['email'] = newCompany.email
    response = JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=json.loads(json.dumps(created_company, cls=CustomJSONEncoder)))
    return response


class OrderBy(str, Enum):
    """
    Sort order of returned list of objects
    """
    ALPHABETICAL_ASC = "ALPHABETICAL_ASC"
    ALPHABETICAL_DESC = "ALPHABETICAL_DESC"
    CREATED_AT_DATE_ASC = "CREATED_AT_DATE_ASC"
    CREATED_AT_DATE_DESC = "CREATED_AT_DATE_DESC"
    UPDATED_AT_DATE_ASC = "UPDATED_AT_DATE_ASC"
    UPDATED_AT_DATE_DESC = "UPDATED_AT_DATE_DESC"


@router.get("/companies", response_model=list[CompanyInDB])
async def get_companies(
        request: Request,
        regex: str | None = Query(
            "", description="Regex to filter by company names"),
        orderBy: OrderBy | None = Query(
            default=OrderBy.ALPHABETICAL_ASC,
            description="Sort order for companies, case-insensitive."),
        userId=Depends(auth_handler.auth_wrapper)):
    '''
    Get All companies along with each company's users. 
    Regex query parameter filters by company name.
    '''
    await get_and_check_user(userId, request)  # checks if user exists and is active

    sort_order = {
        "CREATED_AT_DATE_ASC": [{"$sort": {"dateCreated": 1}}],
        "CREATED_AT_DATE_DESC": [{"$sort": {"dateCreated": -1}}],
        "UPDATED_AT_DATE_ASC": [{"$sort": {"lastUpdated": 1}}],
        "UPDATED_AT_DATE_DESC": [{"$sort": {"lastUpdated": -1}}],
        "ALPHABETICAL_ASC":  [
            # sort in a case-insensitive way requires the below 3 steps in the pipeline
            {"$addFields": {"lowercaseCompanyName": {"$toLower": "$companyName"}}},
            {"$sort": {"lowercaseCompanyName": 1}},
            {"$project": {"lowercaseCompanyName": 0}}
        ],
        "ALPHABETICAL_DESC": [
            {"$addFields": {"lowercaseCompanyName": {"$toLower": "$companyName"}}},
            {"$sort": {"lowercaseCompanyName": -1}},
            {"$project": {"lowercaseCompanyName": 0}}
        ],
    }[orderBy.name]

    pipeline = [
        {"$match": {"companyName": {"$regex": regex}}},
        {"$addFields": {"companyId": {"$toString": "$_id"}}},
    ]
    # Apply sorting if specified
    if sort_order:
        pipeline.extend(sort_order)

    pipeline.append({"$project": {"_id": 0}})
    companies = await request.app.mongodb["companies"].aggregate(pipeline).to_list(length=250)
    for company in companies:
        admin = await request.app.mongodb["users"].find_one(
            {"_id": ObjectId(company["adminId"])})
        company["email"] = admin["email"]
        company["firstName"] = admin["firstName"]
        company["lastName"] = admin["lastName"]
        # get all users for company
        # TODO:  search by comapnyId instead of company name; each user should have an associated companyId,
        #        rather than a companyName.  
        pipeline = [
            {"$match": {"companyName": company["companyName"]}},
            {"$addFields": {"id": {"$toString": "$_id"}}},
            {"$project": {"_id": 0}},
        ]
        users = await request.app.mongodb["users"].aggregate(pipeline).to_list(length=100)
        company["users"] = users
    return companies


class CompanyUpdate(BaseModel):
    companyName: str | None = Field(
        None,
        description="Name of User's company",
        example="XYZ Trucking")
    tokenUsage: int | None = Field(
        None, description="Number of tokens used", example=750)
    tokenAllotment: int = Field(
        None, description="Tokens alloted to company", example=5000)
    isActive: bool | None = Field(
        None,
        description="Indicates whether the company is active or not",
        example=True)
    adminId: str | None = Field(
        None,
        description="ID of user who is main admin for company",
        example="642ba6e1e51bcf4c8ea23c4d")


@ router.put("/companies/{companyId}", response_model=CompanyUpdate)
async def update_company(request: Request, companyId: str, updatedCompany: CompanyUpdate, userId=Depends(auth_handler.auth_wrapper)):
    '''Update the company information.  Only put needed key/value pairs in the JSON body.  '''
    currentUser: UserBase = await get_and_check_user(userId, request)
    check_user_permissions(currentUser, allowed_user_types=[UserType.KURIOUS_SUPERUSER, UserType.KURIOUS_SALES])

    update = updatedCompany.dict(exclude_unset=True)
    update['lastUpdated'] = datetime.now(timezone.utc)
    result = await request.app.mongodb["companies"].update_one({"_id": ObjectId(companyId)}, {"$set": update})
    if result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return updatedCompany


@ router.delete("/companies/{companyId}")
async def delete_company(request: Request, companyId: str, userId=Depends(auth_handler.auth_wrapper)):
    currentUser: UserBase = await get_and_check_user(userId, request)
    check_user_permissions(currentUser, allowed_user_types=[UserType.KURIOUS_SUPERUSER, UserType.KURIOUS_SALES])

    result = await request.app.mongodb["companies"].delete_one({"_id": ObjectId(companyId)})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return {"status": "success"}


@router.patch("/companies/{companyId}/status")
async def company_status(
        request: Request,
        companyId: str,
        isActive: bool | None = True,
        userId=Depends(auth_handler.auth_wrapper)):
    currentUser: UserBase = await get_and_check_user(userId, request)
    check_user_permissions(currentUser, allowed_user_types=[UserType.KURIOUS_SUPERUSER, UserType.KURIOUS_SALES])

    result = await request.app.mongodb["companies"].update_one(
        {"_id": ObjectId(companyId)},
        {"$set": {"isActive": isActive,
                  "lastUpdated": datetime.now(timezone.utc)}}
    )
    if result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return {"status": "success"}

