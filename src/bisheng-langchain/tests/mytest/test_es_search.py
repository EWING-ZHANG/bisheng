import os
import math
import time
import langchain
from langchain.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document
from bisheng_langchain.vectorstores import ElasticKeywordsSearch
import requests
from langchain.embeddings.base import Embeddings

class OllamaEmbeddings(Embeddings):
    def __init__(self, endpoint: str):
        self.endpoint = endpoint

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        embeddings = []
        for text in texts:
            response = requests.post(
                self.endpoint,
                json={"inputs": text},
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            embeddings.append(response.json()["embedding"])
        return embeddings

    def embed_query(self, text: str) -> list[float]:
        response = requests.post(
            self.endpoint,
            json={"inputs": text},
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        return response.json()["embedding"]

# 使用自定义 Embedding 类
embeddings = OllamaEmbeddings(endpoint="http://localhost:11434/embedding")

# 发送请求到 Ollama 模型 API
def query_llama(prompt: str) -> str:
    url = "http://127.0.0.1:11434"  # 替换为 Ollama 模型 API 地址
    headers = {
        "Content-Type": "application/json",
    }
    data = {
        "inputs": prompt,
    }
    response = requests.post(url, json=data, headers=headers)
    return response.json()["choices"][0]["text"]

# 使用自定义的函数来与 Llama3.2 进行交互
class CustomLLM:
    def __init__(self):
        pass

    def __call__(self, prompt: str):
        return query_llama(prompt)

# 实例化自定义 LLM
llm = CustomLLM()

def data_loader():
    start_time = time.time()
    file_path = "/data/doc/mobipdf-organized.pdf"
    loader = PyPDFLoader(file_path)

    documents = loader.load()
    print('documents:', len(documents))
    print('load pdf time:', time.time() - start_time)

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=0)
    split_docs = text_splitter.split_documents(documents)
    print('split_docs:', len(split_docs))

    start_time = time.time()
    es_store = ElasticKeywordsSearch.from_documents(
        split_docs,
        embeddings,
        llm=llm,
        elasticsearch_url="http://127.0.0.1:9200",
        index_name="zhaogushuglx_keyword_chunk500",
        ssl_verify=False,
    )
    keyword_retriever = es_store.as_retriever(search_type="similarity_score_threshold", search_kwargs={"k": 4, "score_threshold": 0.0})
    print('keyword store time:', time.time() - start_time)

    return keyword_retriever, es_store


def retrieval(query, keyword_retriever):
    print('---------------------------------------------')
    print(keyword_retriever.get_relevant_documents(query))

keyword_retriever, es_store = data_loader()
retrieval("what is rag?", keyword_retriever)
es_store.delete()
