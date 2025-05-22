from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response
import httpx
import os
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import logging
import uvicorn
from uvicorn.config import LOGGING_CONFIG

# Custom logging filter to suppress INFO logs for /health
class HealthCheckFilter(logging.Filter):
    def filter(self, record):
        # Suppress INFO logs for health check requests
        if record.levelno <= logging.INFO and "GET /health " in record.getMessage():
            return False
        return True

# Configure logging
logging_config = LOGGING_CONFIG.copy()
logger = logging.getLogger("uvicorn.access")
logger.setLevel(logging.WARNING)  # Set default level to WARNING
logger.addFilter(HealthCheckFilter())  # Add filter for health checks

# Custom key function to extract api_key from headers or query params
def get_api_key(request: Request) -> str:
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        api_key = request.query_params.get("api_key")
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required in 'X-API-Key' header or 'api_key' query parameter")
    return api_key

# Initialize rate limiter with custom key function
limiter = Limiter(key_func=get_api_key)

# FastAPI app setup
app = FastAPI(
    title="Dhwani API Proxy",
    description="A proxy that forwards all requests to the Dhwani API target server.",
    version="1.0.0",
    redirect_slashes=False,
)

# Add rate limit exceeded handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Target server to forward requests to
TARGET_SERVER = os.getenv("DWANI_API_BASE_URL", "http://localhost:8000")

# Catch-all route to forward all requests with rate limiting
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
@limiter.limit("5/minute")  # Limit to 5 requests per minute per api_key
async def proxy(request: Request, path: str):
    target_url = f"{TARGET_SERVER}/{path}"
    query_params = dict(request.query_params)
    headers = {
        key: value for key, value in request.headers.items()
        if key.lower() not in ("host", "connection", "accept-encoding")
    }
    body = await request.body()
    
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            response = await client.request(
                method=request.method,
                url=target_url,
                params=query_params,
                headers=headers,
                content=body,
                follow_redirects=False
            )
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.headers.get("content-type", "application/json")
            )
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Target server timeout")
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=str(e))
        except httpx.RequestError as e:
            raise HTTPException(status_code=500, detail=f"Failed to forward request: {str(e)}")

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=7860,
        log_config=logging_config,  # Use custom logging configuration
        log_level="warning"  # Set Uvicorn log level to warning
    )