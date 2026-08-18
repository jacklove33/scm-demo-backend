from fastapi import APIRouter

from app.modules.attachments.presentation.router import router as attachment_router
from app.modules.audit.presentation.router import router as audit_router
from app.modules.auth.presentation.router import router as auth_router
from app.modules.customer_pos.presentation.router import router as customer_po_router
from app.modules.customers.presentation.router import router as customer_router
from app.modules.dashboard.presentation.router import router as dashboard_router
from app.modules.edi.presentation.router import router as edi_router
from app.modules.iam.presentation.router import router as iam_router
from app.modules.products.presentation.router import router as product_router
from app.modules.suppliers.presentation.router import router as supplier_router

api_router = APIRouter()
api_router.include_router(attachment_router)
api_router.include_router(auth_router)
api_router.include_router(audit_router)
api_router.include_router(iam_router)
api_router.include_router(customer_router)
api_router.include_router(customer_po_router)
api_router.include_router(dashboard_router)
api_router.include_router(edi_router)
api_router.include_router(supplier_router)
api_router.include_router(product_router)
