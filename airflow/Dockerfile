FROM apache/airflow:2.8.1-python3.11

USER root

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    default-libmysqlclient-dev \
    pkg-config \
    netcat-traditional \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli docker-buildx-plugin \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY start-airflow.sh /start-airflow.sh
RUN chmod +x /start-airflow.sh

USER airflow

COPY requirements.txt /requirements.txt

RUN pip install --no-cache-dir \
    apache-airflow-providers-mysql==5.5.2 \
    mysql-connector-python==8.2.0 \
    pymysql==1.1.0

RUN pip install --no-cache-dir -r /requirements.txt

WORKDIR /opt/airflow
