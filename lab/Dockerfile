# One image for every lab role: `server`, `agent` and `check` (see kavrynt_lab.cli).
# PYTHON_IMAGE lets scripts/lab.sh pull the base image through a Docker Hub mirror.
ARG PYTHON_IMAGE=python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f

FROM ${PYTHON_IMAGE} AS build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /src
COPY pyproject.toml constraints.txt ./
COPY src ./src
RUN python -m venv /opt/lab && /opt/lab/bin/pip install -c constraints.txt .

FROM ${PYTHON_IMAGE}
COPY --from=build /opt/lab /opt/lab
ENV PATH=/opt/lab/bin:$PATH PYTHONUNBUFFERED=1
USER 10001:10001
EXPOSE 8080 9100
ENTRYPOINT ["kavrynt-lab"]
