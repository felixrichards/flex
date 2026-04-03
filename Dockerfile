FROM ghcr.io/oracle/oraclelinux10-python:3.12

RUN groupadd champsget -g 1000 && useradd champsget -g 1000 -m -u 1000
RUN mkdir -p /app && chown champsget:champsget /app

USER champsget
WORKDIR /app

ADD pyproject.toml poetry.lock README.md ./
ADD champs champs
RUN python3 -m pip install . \
    && python3 -m pip uninstall -y opencv-python opencv-contrib-python opencv-python-headless || true \
    && python3 -m pip install --no-cache-dir --force-reinstall --no-deps opencv-python-headless==4.13.0.92

CMD python3 -m champs
