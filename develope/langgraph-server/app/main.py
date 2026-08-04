from fastapi import FastAPI

app = FastAPI(title="gamer_publisher LangGraph Report Service")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
