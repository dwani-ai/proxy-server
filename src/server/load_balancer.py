from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response
import httpx
import os
from itertools import cycle
from typing import List,Dict
import asyncio
import logging
from urllib.parse import urlparse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app setup
app = FastAPI(
    title="Dhwani API Load Balancer",
    description="Load balancer for Dhwani API proxy servers with rate limiting.",
    version="1.0.0",
    redirect_slashes=False,
)

# Custom key function to extract api_key from headers or query params
def get_api_key(request: Request) -> str:
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        api_key = request.query_params.get("api_key")
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required in 'X-API-Key' header or 'api_key' query parameter")
    return api_key

# Initialize rate limiter with custom key function
RATE_LIMIT = os.getenv("RATE_LIMIT", "3/minute")  # Configurable via environment variable
limiter = Limiter(key_func=get_api_key)

# Add rate limit exceeded handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Load backend servers from environment variable
BACKEND_SERVERS_ENV = os.getenv("BACKEND_SERVERS")
if not BACKEND_SERVERS_ENV:
    raise ValueError("Environment variable 'BACKEND_SERVERS' is required")

# Parse comma-separated list of server URLs and validate
BACKEND_SERVERS = [server.strip() for server in BACKEND_SERVERS_ENV.split(",") if server.strip()]
if not BACKEND_SERVERS:
    raise ValueError("No valid backend servers found in 'BACKEND_SERVERS'")

# Validate URLs
for server in BACKEND_SERVERS:
    try:
        result = urlparse(server)
        if not all([result.scheme, result.netloc]):
            raise ValueError(f"Invalid server URL: {server}")
    except Exception as e:
        raise ValueError(f"Invalid server URL: {server} - {str(e)}")

# Health status of each server
server_health: Dict[str, bool] = {server: True for server in BACKEND_SERVERS}

# Round-robin iterator for healthy servers
healthy_servers = cycle(BACKEND_SERVERS)

# Health check interval (seconds)
HEALTH_CHECK_INTERVAL = 30

async def health_check():
    """Periodically check the health of backend servers."""
    async with httpx.AsyncClient(timeout=5) as client:
        while True:
            for server in BACKEND_SERVERS:
                try:
                    response = await client.get(f"{server}/health")
                    server_health[server] = response.status_code == 200
                    logger.info(f"Health check for {server}: {'Healthy' if server_health[server] else 'Unhealthy'}")
                except httpx.RequestError:
                    server_health[server] = False
                    logger.warning(f"Health check failed for {server}")
            await asyncio.sleep(HEALTH_CHECK_INTERVAL)

@app.on_event("startup")
async def startup_event():
    """Start the health check loop on startup."""
    asyncio.create_task(health_check())

def get_next_healthy_server() -> str:
    """Get the next healthy server using round-robin."""
    for _ in range(len(BACKEND_SERVERS)):
        server = next(healthy_servers)
        if server_health.get(server, False):
            return server
    raise HTTPException(status_code=503, detail="No healthy servers available")

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
@limiter.limit(RATE_LIMIT)
async def load_balancer(request: Request, path: str):
    """Forward requests to one of the backend proxy servers with rate limiting."""
    # Get the next healthy server
    target_server = get_next_healthy_server()
    target_url = f"{target_server}/{path}"

    # Prepare query parameters and headers
    query_params = dict(request.query_params)
    headers = {
        key: value for key, value in request.headers.items()
        if key.lower() not in ("host", "connection", "accept-encoding")
    }

    # Get the request body, if any
    body = await request.body()

    # Forward the request
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
            logger.info(f"Forwarded request to {target_server}, status: {response.status_code}")
            
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.headers.get("content-type", "application/json")
            )
        except httpx.TimeoutException:
            server_health[target_server] = False
            logger.warning(f"Timeout on {target_server}, marking as unhealthy")
            raise HTTPException(status_code=504, detail="Target server timeout")
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error from {target_server}: {str(e)}")
            raise HTTPException(status_code=e.response.status_code, detail=str(e))
        except httpx.RequestError as e:
            server_health[target_server] = False
            logger.warning(f"Request error on {target_server}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to forward request: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)