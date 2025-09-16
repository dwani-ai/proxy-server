from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response
import httpx
import os
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

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
    debug=False,  # Disable debug mode for production
)

# Step 2: Secure CORS Configuration
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://dwani.ai", "https://app.dwani.ai",  "https://workshop.dwani.ai"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type", "Accept"],
)

# Add rate limit exceeded handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Target server to forward requests to
TARGET_SERVER = os.getenv("DWANI_API_BASE_URL", "http://localhost:8000")

# Catch-all route with restricted headers (Step 8, JSON validation removed)
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
@limiter.limit("100/minute")
async def proxy(request: Request, path: str):
    target_url = f"{TARGET_SERVER}/{path}"
    query_params = dict(request.query_params)
    headers = {
        key: value for key, value in request.headers.items()
        if key.lower() not in ("host", "connection", "accept-encoding", "user-agent", "referer")
    }
    body = await request.body()
    async with httpx.AsyncClient(timeout=6000) as client:
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)  # Internal port for Nginx