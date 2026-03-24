FROM python:3.15-rc-alpine3.22

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY src /app/src

RUN pip install --no-cache-dir .

EXPOSE 8080

CMD ["python", "-m", "memoria"]
