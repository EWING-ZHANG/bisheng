FROM python:3.10-slim

WORKDIR /app

RUN echo \
    deb https://mirrors.aliyun.com/debian/ bookworm main non-free non-free-firmware contrib \
    deb-src https://mirrors.aliyun.com/debian/ bookworm main non-free non-free-firmware contrib \
    deb https://mirrors.aliyun.com/debian-security/ bookworm-security main \
    deb-src https://mirrors.aliyun.com/debian-security/ bookworm-security main \
    deb https://mirrors.aliyun.com/debian/ bookworm-updates main non-free non-free-firmware contrib \
    deb-src https://mirrors.aliyun.com/debian/ bookworm-updates main non-free non-free-firmware contrib \
    deb https://mirrors.aliyun.com/debian/ bookworm-backports main non-free non-free-firmware contrib \
    deb-src https://mirrors.aliyun.com/debian/ bookworm-backports main non-free non-free-firmware contrib \
    > /etc/apt/sources.list


# Install Poetry
RUN apt-get update && apt-get install gcc g++ curl build-essential postgresql-server-dev-all -y
RUN apt-get update && apt-get install procps -y
# Install font
RUN apt install vim fonts-wqy-zenhei -y
# opencv
RUN apt-get update && apt-get install -y libglib2.0-0 libsm6 libxrender1 libxext6 libgl1 \
    ca-certificates \
    && update-ca-certificates
# RUN curl -sSL https://install.python-poetry.org | python3 - --version 1.8.2
# 安装Poetry并设置PATH
# RUN curl -sSL --insecure https://install.python-poetry.org | python3 - --version 1.8.2 \
#     && export PATH="/root/.local/bin:$PATH" \
#     && poetry --version
# # # Add Poetry to PATH
# ENV PATH="${PATH}:/root/.local/bin"


# 安装 Poetry
RUN curl -sSL --insecure https://install.python-poetry.org | python3 - --version 1.8.2
# 检查 /root/.local/bin 是否存在 poetry
RUN [ -f /root/.local/bin/poetry ] || echo "Poetry not found in /root/.local/bin!" && exit 1
# 更新 PATH 并验证 poetry 版本
ENV PATH="/root/.local/bin:${PATH}"
RUN poetry --version
# # Copy the pyproject.toml and poetry.lock files
# COPY poetry.lock pyproject.toml ./
# Copy the rest of the application codes
COPY ./pyproject.toml ./
COPY bisheng_langchain-0.3.6.dev1.tar.gz ./

RUN python -m pip install --upgrade pip && \
    pip install shapely==2.0.1
# 使用官方地址拉取pypi依赖
# RUN poetry config --unset repositories.tsinghua && \
#     poetry config --unset repositories.aliyun && \
#     poetry config --unset repositories.dataelem-index

# Install dependencies
RUN poetry config virtualenvs.create false
RUN poetry install --no-interaction --no-ansi --without dev

# install nltk_data
RUN python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab'); nltk.download('averaged_perceptron_tagger'); nltk.download('averaged_perceptron_tagger_eng'); nltk.download('wordnet')"

CMD ["sh entrypoint.sh"]
