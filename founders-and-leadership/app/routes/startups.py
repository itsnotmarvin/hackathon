from fastapi import APIRouter

from app.database import supabase

router = APIRouter()


@router.post("/startups")
def create_startup(startup: dict):

    response = (
        supabase
        .table("startups")
        .insert(startup)
        .execute()
    )

    return response.data