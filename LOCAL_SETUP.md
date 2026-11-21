# Windows local setup

Run `./scripts/check-environment.ps1` to inspect RAM, CPU, graphics adapters, storage and tool availability. CUDA is not required. Budget approximately 8–16 GB RAM for development plus a small local language model; actual capacity depends on model quantization, context size and concurrent apps. These are planning estimates, not measured performance guarantees.

1. Install uv, Python 3.12, Node.js 22 LTS, and Ollama from their official installers.
2. Run `./scripts/setup.ps1`. The project uses npm and its lockfile for the frontend.
3. Start Ollama and run `ollama pull qwen2.5:3b`. Initial model and embedding downloads require internet.
4. Set `.env` from `.env.example`. Never commit secrets.
5. Run `./scripts/start-api.ps1`; start `npm run dev` in `apps/web` separately.
6. Register, upload supported documents, invoke the administrator ingestion worker, and verify ready status before retrieval.

The API loads `.env`; standalone benchmark processes need their environment variables exported in PowerShell. Example: `$env:QDRANT_PATH=':memory:'`. Tests inject provider doubles explicitly; normal application requests never silently switch to deterministic embeddings.

Optional Docker: set a database password for this shell before starting, for example `$env:POSTGRES_PASSWORD = 'choose-a-long-random-value'` in PowerShell. Compose refuses to start without it, and the same value is used by both the API and PostgreSQL. Then run `docker compose -f infra/docker/compose.yaml up --build -d`, followed by `docker compose -f infra/docker/compose.yaml exec ollama ollama pull qwen2.5:3b`. The Ollama image is pinned to `ollama/ollama:0.12.3`; bump it deliberately. Ollama is published only on `127.0.0.1:11434`, so it is not reachable from other machines on your network. Start the frontend on the host. Docker requires a functioning Docker Desktop/WSL2 installation. Default ONNX reranking uses FastEmbed; the optional sentence-transformers adapter requires the reranking extra.

To prepare the fictional demo: run `uv run python -m rag_api.cli init`, then `uv run python -m rag_api.cli seed-demo --process`. Import measured evaluation results with `uv run python -m rag_api.cli import-evaluation --workspace fictional-demo-workspace --report datasets/results/local-onnx.json`. Set `DEMO_ENABLED=true` and `DEMO_WORKSPACE_ID=fictional-demo-workspace` before starting the API.

Qdrant embedded storage supports one owning process. Use the UI's bounded ingestion endpoint while the API is running. Stop the API before running a standalone worker/seed process against the same Qdrant directory. Hosted Pinecone supports separate API and worker processes.

Local PostgreSQL data, source files and Ollama weights use Docker volumes. The Compose database user and password are set from `POSTGRES_PASSWORD` (no default), and its SQL port is not published. Back up volumes before destructive Docker cleanup.

Optional scanned-PDF OCR: install Poppler (`pdftoppm`) and Tesseract separately, set their executable paths in `.env`, and enable `OCR_ENABLED=true`. Each subprocess has a 30-second timeout; raster size and the number of OCR pages (10 per document) are bounded. Real OCR accuracy has not been measured in this environment. Default behavior is an explicit OCR-required failure.
