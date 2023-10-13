from enum import Enum
from bson import ObjectId
import json
from datetime import datetime, timezone
from pydantic import EmailStr, Field, BaseModel, validator, conint
from email_validator import validate_email, EmailNotValidError
import pytz
import json


class CustomJSONEncoder(json.JSONEncoder):
    """
    Custom encoder to handle ObjectId and datetime.datetime objects
    """
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.replace(tzinfo=pytz.utc).isoformat()
        return super(CustomJSONEncoder, self).default(obj)


class UserType(str, Enum):
    """
    Represents the possible roles that a user can have.
    """
    KURIOUS_SUPERUSER = "KURIOUS_SUPERUSER"
    KURIOUS_SALES = "KURIOUS_SALES"
    CLIENT_ADMIN = "CLIENT_ADMIN"
    CLIENT_USER = "CLIENT_USER"


def password_validator(v):
    """
    Validate that password is strong enough:
    - At least 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    """
    if len(v) < 8:
        raise ValueError('password must be at least 8 characters')
    if not any(char.isupper() for char in v):
        raise ValueError('password must contain at least one uppercase letter')
    if not any(char.islower() for char in v):
        raise ValueError('password must contain at least one lowercase letter')
    if not any(char.isdigit() for char in v):
        raise ValueError('password must contain at least one digit')
    return v


class Meta(BaseModel):
    page: int = Field(
        ...,
        description="The page number of the paginated results. Each page will display a fixed number of items specified by the pagesize parameter.",
        example=11)
    pageSize: int = Field(
        ...,
        description="The maximum number of items to be displayed per page in the paginated results.", example=20)
    totalCount: int = Field(
        ...,
        description="The total number of user records available in the database given the optional query parameters.",
        example=201)


class LoginBase(BaseModel):
    email: EmailStr = Field(..., example='user1@gmail.com')
    password: str = Field(..., example='ABCdef123!')


class LoginResponse(BaseModel):
    id: str = Field(..., description="24 hexadecimal character unique user id.",
                    example="642ba6e1e51bcf4c8ea23c4d")
    email: str = Field(..., description="email of logged in user.",
                       example="bill.smith@monarchconnected.com")
    userType: str = Field(..., description="Role of user",
                          example="KURIOUS_SALES")
    token: str = Field(..., description="JSON Web Token (JWT)",
                       example="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE2ODA1ODQ2NjIsImlhdCI6MTY4MDU4MjU2Miwic3ViIjoiNjQyYmE2ZTFlNTFiY2Y0YzhlYTIzYzRkIn0.Pbe5w03f7DoHhsw26zBTL_QI14ayfnoM_w0VtD_XUyI")


class RegisterUser(BaseModel):
    email: EmailStr = Field(..., example='user1@gmail.com')
    password: str = Field(..., description='Password must be at least 8 characters and have at least one uppercase, one lower case letter and one number.', example='ABCdef123!')
    firstName: str = Field(..., example='Bill')
    lastName: str = Field(..., example='Smith')
    phoneNumber: str = Field(..., example='212-123-1234')
    companyName: str = Field(
        ..., description="User's company", example="Company ABC")
    userType: UserType = Field(default=UserType.CLIENT_USER)

    @validator('password')
    def password_strength(cls, v):
        p = password_validator(v)
        return p


class UserBase(BaseModel):
    username: str = Field(
        ..., min_length=3,
        max_length=40,
        description="username is same as email",
        example='bill.smith@gmail.com')
    email: EmailStr = Field(..., example='bill.smith@gmail.com')
    firstName: str = Field(..., example='Bill')
    lastName: str = Field(..., example='Smith')
    phoneNumber: str = Field('', examples=['212-123-1234'])
    companyName: str = Field(
        ...,
        description="Name of User's company",
        example="XYZ Trucking")
    userType: UserType = Field(default=UserType.CLIENT_USER)
    accountStatus: str = Field(
        default="ACTIVE",
        description="Indicates whether user account is PENDING, ACTIVE, or DEACTIVATED",
        example="ACTIVE"
    )
    lastLogin: datetime = Field(
        default=datetime.now(timezone.utc),
        description="The date and time of the user's last login in iso format with microseconds and with a UTC offset",
        example="2023-03-17T14:30:00.000000+00:00")
    dateJoined: datetime = Field(
        default=datetime.now(timezone.utc),
        description="The date and time when the user joined in iso format with microseconds and with a UTC offset",
        example="2023-03-17T14:30:00.000000+00:00")

    @validator("email")
    def valid_email(cls, v):
        try:
            email = validate_email(v).email
            return email
        except EmailNotValidError as e:
            raise EmailNotValidError

    class Config:
        json_encoders = {
            # encode datetime object as isoformated string in local timezone
            # Example: "2023-03-25T01:54:44-04:00"
            datetime: lambda dt: dt.replace(tzinfo=pytz.utc).isoformat()
        }


class UserBaseWithId(UserBase):
    id: str | None = Field(
        ...,
        description='Unique 24 hexadecimal character ID auto-created by database.',
        example='642ba6e1e51bcf4c8ea23c4d'
    )

    def __eq__(self, other):
        if isinstance(other, UserBaseWithId):
            return self.email == other.email
        return False

    def __hash__(self):
        return hash(self.email)


class UserBaseWithPass(UserBase):
    password: str | None = Field(None, example='DiEB7q*H3$nPAy')


class NewCompany(BaseModel):
    companyName: str = Field(..., description="Name of Company",
                             example="XYZ Trucking")
    firstName: str = Field(...,
                           description="First name of admin within Company", example="Bob")
    lastName: str = Field(...,
                          description="Last name of admin within Company", example="Smith")
    tokenAllotment: conint(ge=0, lt=10_000_000) = Field(
        0, description="Tokens alloted to company", example=5000)
    email: EmailStr = Field(...,
                            description="Email address of company admin",
                            example='bill.smith@gmail.com')

    @validator("email")
    def valid_email(cls, v):
        try:
            email = validate_email(v).email
            return email
        except EmailNotValidError as e:
            raise EmailNotValidError


class Company(BaseModel):
    companyId: str | None = Field(
        None, description="24-character unique hexadecimal identifier for the company.",
        example='5f456791b849a8cadda92d04')
    companyName: str = Field(
        ...,
        description="Name of User's company",
        example="XYZ Trucking")
    tokenUsage: int = Field(
        0, description="Number of tokens used", example=750)
    tokenAllotment: int = Field(
        0, description="Tokens alloted to company", example=5000)
    isActive: bool = Field(
        default=True,
        description="Indicates whether the company is active or not",
        example=True)
    adminId: str | None = Field(
        None,
        description="ID of user who is main admin for company",
        example="642ba6e1e51bcf4c8ea23c4d")
    firstName: str = Field(
        None,
        description="First name of company admin",
        example="Bill")
    lastName: str = Field(
        None,
        description="Last name of company admin",
        example="Smith")
    lastUpdated: datetime = Field(
        default=datetime.now(timezone.utc),
        description="The date and time of the last update to any data for this company in iso format with microseconds and with a UTC offset",
        example="2023-03-17T14:30:00.000000+00:00")
    dateCreated: datetime = Field(
        default=datetime.now(timezone.utc),
        description="The date and time when the company account created in iso format with microseconds and with a UTC offset",
        example="2023-03-17T14:30:00.000000+00:00")
