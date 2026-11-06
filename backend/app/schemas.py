from typing import Literal
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator

Status = Literal['Nouveau', 'En cours', 'En attente', 'Résolu']
Priority = Literal['Basse', 'Moyenne', 'Haute']


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Login(Input):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)

    @field_validator('password', mode='before')
    @classmethod
    def exact_password(cls, value):
        # Do not trim secrets: handled by model override below.
        return value

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)


class TicketCreate(Input):
    title: str = Field(min_length=5, max_length=160)
    description: str = Field(min_length=10, max_length=10000)
    category_id: int = Field(gt=0)
    priority: Priority = 'Moyenne'


class TicketPatch(Input):
    status: Status | None = None
    priority: Priority | None = None
    assignee_id: int | None = Field(default=None, gt=0)
    resolution: str | None = Field(default=None, min_length=5, max_length=5000)


class MessageCreate(Input):
    body: str = Field(min_length=1, max_length=10000)
    internal: bool = False


class ProfilePatch(Input):
    name: str = Field(min_length=2, max_length=100)


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class UserState(Input):
    active: bool


class ResetRequest(Input):
    email: EmailStr


class ResetComplete(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(min_length=12, max_length=256)
