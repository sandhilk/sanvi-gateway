from fastapi import FastAPI

app = FastAPI(title="checkout")


@app.get("/health")
def health():
    return {"status": "ok"}
