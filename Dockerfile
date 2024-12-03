FROM ghcr.io/astral-sh/uv:python3.12-alpine
WORKDIR /app
COPY . /app
RUN uv sync
ENTRYPOINT ["uv", "run", "python", "./tweet_updates.py"]
