from fastapi import APIRouter, Depends
from app.core.database import get_db_connection

router = APIRouter()

@router.get("/api/holdings")
def get_holdings():

    return {"data": }