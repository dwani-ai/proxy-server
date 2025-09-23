from fastapi import FastAPI
from fastapi.responses import RedirectResponse
app = FastAPI()

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")

@app.get("/greet")
async def greet():
    return {"message": "Welcome to FastAPI!"}