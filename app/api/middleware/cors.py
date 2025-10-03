from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import logging

logger = logging.getLogger(__name__)


class RobustCORSMiddleware(BaseHTTPMiddleware):
    """Robust CORS middleware that handles database connection issues gracefully"""
    
    def __init__(self, app, enable_logging: bool = True):
        super().__init__(app)
        self.enable_logging = enable_logging
    
    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin", "*")
        
        # Handle preflight requests with robust error handling
        if request.method == "OPTIONS":
            if self.enable_logging:
                logger.info(f"🔧 OPTIONS preflight for {request.url.path} from {origin}")
            
            # Always return 200 for OPTIONS requests, regardless of database status
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
                    "Access-Control-Allow-Headers": "Accept, Accept-Language, Content-Language, Content-Type, Authorization, X-Requested-With, X-Request-Id, Origin, Access-Control-Request-Method, Access-Control-Request-Headers",
                    "Access-Control-Allow-Credentials": "true",
                    "Access-Control-Max-Age": "600",
                    "Access-Control-Expose-Headers": "X-Process-Time-ms, X-Request-Id",
                }
            )
        
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            if self.enable_logging:
                logger.error(f"❌ Request failed: {str(e)}")
            # Return CORS-enabled error response
            return Response(
                status_code=500,
                content='{"detail": "Internal server error"}',
                media_type="application/json",
                headers={
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Credentials": "true",
                }
            )


__all__ = ["CORSMiddleware", "RobustCORSMiddleware"]


