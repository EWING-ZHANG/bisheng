FROM dataelement/bisheng-backend:base.v1

WORKDIR /app
COPY ./ ./
ENV PYTHONPATH="/app:${PYTHONPATH}"

# 安装所有系统依赖（合并步骤）
RUN apt-get update && apt-get install -y \
    supervisor \
    libmariadb-dev \
    libmariadb-dev-compat \
    libssl-dev \
    python3-dev \
    wget \
    gcc \
    g++ \
    libcurl4-openssl-dev \
    libboost-all-dev \
    protobuf-compiler \
    libprotobuf-dev \
    default-libmysqlclient-dev \
    pkg-config \
    curl \
    ca-certificates \
    && mkdir -p /var/log/supervisor \
    && rm -rf /var/lib/apt/lists/* \
    && update-ca-certificates

# 复制配置和脚本
COPY ./supervisord.conf /etc/supervisor/conf.d/
COPY ./launch_backend_service.sh /home/ewing/newProject/bisheng/docker/
RUN chmod +x /home/ewing/newProject/bisheng/docker/launch_backend_service.sh

# 安装 Python 依赖
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false \
    && poetry install --no-root \
    && poetry install

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
