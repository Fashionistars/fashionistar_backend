# scripts/modal_ollama.py
"""
Fashionistar Ollama Serverless Service on Modal.com.

Runs Ollama daemon on a serverless NVIDIA A10G GPU in production.
Acts as a reverse proxy for all Ollama endpoints including streaming generation.

Usage:
  1. Install modal: `pip install modal`
  2. Setup credentials: `modal setup`
  3. Deploy to Modal: `modal deploy scripts/modal_ollama.py`
  4. Copy the resulting URL (e.g. https://<workspace>--fashionistar-ollama-app.modal.run)
     and set it as OLLAMA_HOST in the Render production dashboard environment.
"""

import os
import subprocess
import time
import modal
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

# 1. Define container image with Ollama binary installed
image = (
    modal.Image.debian_slim()
    .apt_install("curl", "ca-certificates")
    .run_commands(
        "curl -L https://ollama.com/download/ollama-linux-amd64.tgz -o /tmp/ollama.tgz",
        "tar -C /usr -xzf /tmp/ollama.tgz",
        "rm /tmp/ollama.tgz"
    )
)

# 2. Define the Modal App
app = modal.App("fashionistar-ollama", image=image)

# 3. Create FastAPI app for routing and proxying
web_app = FastAPI()


@web_app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_to_ollama(path: str, request: Request):
    """
    Reverse proxy forwarding requests to the local Ollama server running inside the container.
    Supports real-time token streaming via HTTP chunked encoding.
    """
    import httpx

    # Format remote target URL
    url = f"http://127.0.0.1:11434/{path}"

    # Extract client headers, payload, and query parameters
    method = request.method
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
    body = await request.body()
    query_params = dict(request.query_params)

    # Initialize async client
    client = httpx.AsyncClient(timeout=300.0)

    # Build and dispatch proxy request
    req = client.build_request(
        method=method,
        url=url,
        headers=headers,
        content=body,
        params=query_params
    )

    response = await client.send(req, stream=True)

    # Stream chunks to client in real-time
    async def generate_chunks():
        try:
            async for chunk in response.aiter_raw():
                yield chunk
        finally:
            await response.aclose()
            await client.aclose()

    return StreamingResponse(
        generate_chunks(),
        status_code=response.status_code,
        headers=dict(response.headers)
    )


# 4. Define Ollama serverless GPU class
@app.cls(
    gpu="A10G",                 # NVIDIA A10G (24GB VRAM) for enterprise speed
    timeout=600,                # 10 minute execution limit
    container_idle_timeout=120, # Warm container for 2 minutes to eliminate cold start on consecutive calls
)
class OllamaService:
    @modal.enter()
    def start_ollama(self):
        """Startup hook: Starts the Ollama daemon and pre-pulls models."""
        # Run Ollama daemon locally
        self.process = subprocess.Popen(
            ["ollama", "serve"],
            env={**os.environ, "OLLAMA_HOST": "127.0.0.1:11434"}
        )

        # Wait until port 11434 is active
        for _ in range(30):
            try:
                import socket
                with socket.create_connection(("127.0.0.1", 11434), timeout=1):
                    break
            except (ConnectionRefusedError, socket.timeout):
                time.sleep(1)
        else:
            raise RuntimeError("Ollama daemon failed to launch on port 11434.")

        # Pre-pull model weights during startup to ensure instant request resolution
        # These will run on A10G GPU in production
        subprocess.run(["ollama", "pull", "llama3.2:3b"], check=True)
        subprocess.run(["ollama", "pull", "nomic-embed-text"], check=True)

    @modal.exit()
    def stop_ollama(self):
        """Shutdown hook: Gracefully terminates the Ollama daemon process."""
        self.process.terminate()
        self.process.wait()

    @app.asgi_app()
    def app(self):
        """Expose the FastAPI app as a serverless web endpoint."""
        return web_app
