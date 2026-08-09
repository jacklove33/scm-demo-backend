from fastapi import APIRouter

from app.modules.customers.presentation.router import router as customer_router
from app.modules.iam.presentation.router import router as iam_router

api_router = APIRouter()
api_router.include_router(iam_router)
api_router.include_router(customer_router)
