from fastapi import FastAPI

app = FastAPI(title="gamer_publisher API")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
