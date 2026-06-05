
    FROM python:3.8-slim
    WORKDIR /usr/src/app
    COPY . .
    RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi
    CMD ["tail", "-f", "/dev/null"]
    