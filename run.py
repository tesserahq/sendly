import uvicorn
from app.config import get_settings


def dev():
    settings = get_settings()
    uvicorn.run("app.main:app", reload=True, port=settings.port)
