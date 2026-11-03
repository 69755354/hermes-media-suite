import uvicorn

from .config import host, port, web_workers


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=host(),
        port=port(),
        workers=web_workers(),
        reload=False,
    )
