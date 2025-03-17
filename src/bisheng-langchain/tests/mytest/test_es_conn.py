from elasticsearch import Elasticsearch

# 配置 Elasticsearch 客户端
es_client = Elasticsearch(
    hosts=["http://127.0.0.1:1200"],  # 主机和端口
    http_auth=("elastic", "infini_rag_flow"),  # 用户名和密码
    verify_certs=False  # 如果是 HTTPS，但不想验证证书
)

# 测试连接
try:
    response = es_client.info()
    print("Connected to Elasticsearch:")
    print(response)
except Exception as e:
    print("Failed to connect to Elasticsearch:", str(e))
