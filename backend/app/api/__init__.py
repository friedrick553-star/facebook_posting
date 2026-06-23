from fastapi import APIRouter

from app.api import auth, dashboard, filters, products, users

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(filters.router)
api_router.include_router(dashboard.router)
api_router.include_router(products.router)
