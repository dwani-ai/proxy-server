from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response
import httpx
import os
# FastAPI app setup
app = FastAPI(
    title="Dhwani API Proxy",
    description="A proxy that forwards all requests to a target server.",
    version="1.0.0",
    redirect_slashes=False,
)

# Target server to forward requests to
TARGET_SERVER = os.getenv("DWANI_API_BASE_URL")  # Replace with the actual target server IP and port


# Catch-all route to forward all requests
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy(request: Request, path: str):
    # Construct the target URL
    target_url = f"{TARGET_SERVER}/{path}"
    
    # Prepare query parameters
    query_params = dict(request.query_params)
    
    # Prepare headers, excluding FastAPI-specific headers
    headers = {
        key: value for key, value in request.headers.items()
        if key.lower() not in ("host", "connection", "accept-encoding")
    }
    
    # Get the request body, if any
    body = await request.body()
    
    # Create an HTTPX client for making the request
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            # Forward the request to the target server
            response = await client.request(
                method=request.method,
                url=target_url,
                params=query_params,
                headers=headers,
                content=body,
                follow_redirects=False
            )
            
            # Return the response directly
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
    uvicorn.run(app, host="0.0.0.0", port=7860)  # Run the proxy server