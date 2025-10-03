from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import time
import logging

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, log_level: str = "INFO"):
        super().__init__(app)
        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
    
    async def dispatch(self, request: Request, call_next):
        # Skip logging for health checks and static files to improve performance
        if request.url.path in ["/health", "/", "/favicon.ico"]:
            return await call_next(request)
        
        origin = request.headers.get("origin", "no-origin")
        logger.info(f"📨 {request.method} {request.url.path} from {origin}")
        
        start = time.perf_counter()
        try:
            response: Response = await call_next(request)
            duration_ms = (time.perf_counter() - start) * 1000
            response.headers["X-Process-Time-ms"] = f"{duration_ms:.2f}"
            
            # Only log detailed info for slower requests or errors
            if duration_ms > 100 or response.status_code >= 400:
                logger.info(f"✅ {request.method} {request.url.path} - {response.status_code} ({duration_ms:.2f}ms)")
            
            return response
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.error(f"❌ {request.method} {request.url.path} - Error: {str(e)} ({duration_ms:.2f}ms)")
            raise


