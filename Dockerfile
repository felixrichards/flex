FROM ghcr.io/oracle/oraclelinux10-python:3.12

RUN groupadd champsget -g 1000 && useradd champsget -g 1000 -m -u 1000
RUN mkdir -p /app && chown champsget:champsget /app

USER champsget
WORKDIR /app

ADD pyproject.toml poetry.lock README.md .
ADD champs champs
RUN python3 -m pip install . \
    && (python3 -m pip show opencv-python >/dev/null 2>&1 && python3 -m pip uninstall -y opencv-python || true) \
    && python3 -m pip install --no-cache-dir --upgrade opencv-python-headless

CMD python3 -m champs