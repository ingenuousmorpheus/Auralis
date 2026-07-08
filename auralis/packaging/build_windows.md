# Windows packaging (Phase 4 target)

Goal: a single `.exe` that launches the backend and serves the built frontend,
so users don't need Python or Node installed.

Sketch:
1. `cd frontend && npm install && npm run build`  → static assets in `frontend/dist`.
2. Serve `frontend/dist` from FastAPI via `StaticFiles` (add in Phase 4).
3. `pyinstaller --onefile --add-data "auralis/engine/profiles;auralis/engine/profiles" \
     --add-data "frontend/dist;frontend/dist" auralis/run.py -n Auralis`
4. Validate the bundle EARLY — native libs (libsndfile, Matchering) must be
   collected. Test on a clean Windows VM with no Python installed.

Not wired up in Phase 1 by design; the design doc lists this as a Phase 4 risk to
de-risk before the end, not after.
