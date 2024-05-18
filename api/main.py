import uvicorn
from fastapi import FastAPI
from .routers import transfer
from .auth import auth_router
from .dependencies import cache_db


logistics_api = FastAPI()
logistics_api.include_router(auth_router)
logistics_api.include_router(transfer.router)


@logistics_api.get("/")
async def root():
    cache_db.hset('contact:123', mapping={
        'name': 'John',
        "surname": 'Smith',
        "company": 'Redis',
        "age": 29
    })
    return {"message": "Hello World"}


@logistics_api.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}


if __name__ == '__main__':
    print("dd")
    uvicorn.run(logistics_api, host="0.0.0.0", port=8000)
