FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["python", "-m", "yingdao_rpa_mcp", "--mock", "--transport", "http", "--host", "0.0.0.0", "--port", "8000"]
