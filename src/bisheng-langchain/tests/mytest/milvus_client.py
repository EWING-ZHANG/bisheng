from pymilvus import connections, Collection

# 连接到 Milvus 服务器
connections.connect("default", host="127.0.0.1", port="19530")

# 指定要查询的集合名称
collection_name = "col_1736657837_f1df3b8c"

# 加载集合
collection = Collection(collection_name)
collection.load()

# 查询集合中的所有数据
# 使用 query() 方法，不指定任何条件
results = collection.query(
    expr="",  # 空字符串表示查询所有数据
    output_fields=["vector", "text"],  # 指定要返回的字段
    limit=1
)

# 打印查询结果
for result in results:
    print(f"vector: {result['vector']}, text: {result['text']}")


# 获取集合对象
collection = Collection(collection_name)

# 获取集合的模式信息
schema = collection.schema

# 打印集合中的所有字段信息
for field in schema.fields:
    print(f"字段名称: {field.name}")
    print(f"数据类型: {field.dtype}")
    print(f"是否为主键: {field.is_primary}")
    print(f"是否自动生成ID: {field.auto_id}")
    print(f"字段描述: {field.description}")
    print(f"向量维度 (仅适用于向量字段): {getattr(field, 'dim', 'N/A')}")
    print("-" * 40)

# 断开连接
connections.disconnect("default")