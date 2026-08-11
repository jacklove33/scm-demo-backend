from fastapi import APIRouter

from app.modules.audit.presentation.router import router as audit_router
from app.modules.auth.presentation.router import router as auth_router
from app.modules.customer_pos.presentation.router import router as customer_po_router
from app.modules.customers.presentation.router import router as customer_router
from app.modules.iam.presentation.router import router as iam_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(audit_router)
api_router.include_router(iam_router)
api_router.include_router(customer_router)
api_router.include_router(customer_po_router)
