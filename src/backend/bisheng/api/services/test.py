from pymilvus import connections, utility

# 连接到 Milvus 服务器（根据你的配置调整参数）
connections.connect(
    alias="default",
    host="localhost",  # Milvus 服务地址
    port="19530"       # Milvus 端口
)

# 列出所有集合名称
collections = utility.list_collections()

# 删除所有集合
for collection_name in collections:
    print(f"Dropping collection: {collection_name}")
    utility.drop_collection(collection_name)

print("All collections have been deleted.")