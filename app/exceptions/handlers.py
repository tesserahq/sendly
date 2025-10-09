from traceback import format_exc
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from app.exceptions.resource_not_found_error import ResourceNotFoundError


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ResourceNotFoundError)
    async def resource_not_found_handler(request: Request, exc: ResourceNotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(exc)},
        )

    @app.exception_handler(Exception)
    async def debug_exception_handler(request: Request, exc: Exception):

        tracback_msg = format_exc()
        return JSONResponse(
            {
                "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": f"error info: {tracback_msg}",
                # "message": f"error info: {str(exc)}",
                "data": "",
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
