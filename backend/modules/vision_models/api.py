from fastapi import APIRouter

from backend.modules.vision_models.dataset_api import router as dataset_router
from backend.modules.vision_models.project_api import router as project_router
from backend.modules.vision_models.training_api import router as training_router

router = APIRouter(prefix="/vision", tags=["agricultural-vision"])
router.include_router(project_router)
router.include_router(dataset_router)
router.include_router(training_router)
