"""Launch the Auralis backend. Usage: `auralis` or `python -m auralis.run`."""
import uvicorn

def main():
    # 127.0.0.1 only — no external listener.
    uvicorn.run("auralis.api.main:app", host="127.0.0.1", port=8000, reload=False)

if __name__ == "__main__":
    main()
