FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic

RUN uv pip install --system --no-cache .

RUN mkdir -p \
    ./data/images/question_images \
    ./data/images/option_images \
    ./data/images/analysis_images \
    ./data/images/formula_images \
    ./data/logs \
    ./data/exports

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
