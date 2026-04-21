FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN pip install --no-cache-dir uv
RUN uv sync --frozen --no-install-project --no-dev

COPY pulumik8s ./pulumik8s

WORKDIR /app/pulumik8s

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
