FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY mcp_google_workspace/ mcp_google_workspace/

RUN pip install --no-cache-dir .

ENV MCP_TRANSPORT=streamable-http
ENV PORT=8080

EXPOSE 8080

CMD ["python", "-m", "mcp_google_workspace"]
