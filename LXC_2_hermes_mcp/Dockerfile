FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir fastapi "fastapi-mcp" "mcp<2" uvicorn[standard] python-frontmatter aiofiles && rm pyproject.toml
COPY server.py .
CMD ["python", "server.py"]