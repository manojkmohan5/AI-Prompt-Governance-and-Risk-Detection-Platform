from fastapi import APIRouter

from app.api.v1.endpoints import auth, audit, knowledge_shield, policies, prompts, analytics

router = APIRouter()

router.include_router(auth.router)
router.include_router(prompts.router)
router.include_router(analytics.router)
router.include_router(policies.router)
router.include_router(knowledge_shield.router)
router.include_router(audit.router)
