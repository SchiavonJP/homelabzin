FROM python:3.14-slim@sha256:af8a5aa14780025dbfbcfbc81bd8a91ebd87711dd5b0f48ed71090949dd7cb1d AS backend
WORKDIR /app
COPY backend/pyproject.toml ./
COPY backend/requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY backend/app ./app
RUN pip install --no-cache-dir --no-deps .
RUN python -m app.schema > /app/openapi.json
COPY backend/tests ./tests
RUN --mount=type=tmpfs,target=/tmp/xereta-tests python -m pytest -q --basetemp=/tmp/xereta-tests/cases

FROM oven/bun:1@sha256:1d22548f177f4ff38e0c15baa3c2c46c6c2060ba2d1bc573bb4720b407548f1d AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile
COPY frontend ./
COPY --from=backend /app/openapi.json /app/openapi.json
RUN bun run test:unit && bun run generate-client && bun run build

FROM backend AS runtime
COPY --from=frontend /app/frontend/dist ./app/frontend
COPY ops ./ops
RUN useradd --uid 10001 --create-home xereta && mkdir /data && chown xereta:xereta /data
USER xereta
EXPOSE 3101
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "3101", "--no-access-log"]
