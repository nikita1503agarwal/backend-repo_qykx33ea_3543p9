"""
Database Schemas for PERMA app

Each Pydantic model corresponds to one MongoDB collection (lowercased class name).
"""
from typing import Optional, List, Literal
from pydantic import BaseModel, Field
from datetime import date

# -------- PERMA core schemas --------
class CheckIn(BaseModel):
    """Daily PERMA check-in
    Collection: "checkin"
    """
    user_id: Optional[str] = Field(None, description="Anonymous or account id")
    date: str = Field(default_factory=lambda: date.today().isoformat(), description="YYYY-MM-DD")
    p: int = Field(..., ge=0, le=10, description="Positive Emotions")
    e: int = Field(..., ge=0, le=10, description="Engagement")
    r: int = Field(..., ge=0, le=10, description="Relationships")
    m: int = Field(..., ge=0, le=10, description="Meaning")
    a: int = Field(..., ge=0, le=10, description="Accomplishment")
    note: Optional[str] = Field(None, description="Short reflection for the day")

class Goal(BaseModel):
    """PERMA-aligned goal
    Collection: "goal"
    """
    user_id: Optional[str] = None
    title: str
    dimension: Literal['P','E','R','M','A']
    cadence: Literal['daily','weekly','adhoc'] = 'daily'
    status: Literal['active','done','archived'] = 'active'
    progress: int = Field(0, ge=0, le=100)

class Reflection(BaseModel):
    """Free-form reflections
    Collection: "reflection"
    """
    user_id: Optional[str] = None
    text: str
    tags: List[str] = []
    date: str = Field(default_factory=lambda: date.today().isoformat())

# Optional lightweight user for future extension
class User(BaseModel):
    user_id: str
    locale: str = 'da'
