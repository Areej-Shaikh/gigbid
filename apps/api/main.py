from fastapi import FastAPI

app = FastAPI(title="GigBid API")

@app.get("/health")
def health():
    return {"status": "ok"}