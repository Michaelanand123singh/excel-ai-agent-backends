from fastapi import Request
from fastapi.responses import JSONResponse


async def http_error_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": str(exc)})


