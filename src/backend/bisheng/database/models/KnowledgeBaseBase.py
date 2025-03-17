from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Column, text
from sqlalchemy.dialects.mysql import BIGINT, TEXT
from sqlalchemy import DateTime

class KnowledgeBaseBase(SQLModel, table=True):
    __tablename__ = "knowledgebase"

    id: Optional[str] = Field(default=None, primary_key=True, max_length=32)
    create_time: Optional[int] = Field(sa_column=Column(BIGINT), index=True)
    create_date: Optional[datetime] = Field(
        sa_column=Column(DateTime, server_default=text('CURRENT_TIMESTAMP')),
        index=True
    )
    update_time: Optional[int] = Field(sa_column=Column(BIGINT), index=True)
    update_date: Optional[datetime] = Field(
        sa_column=Column(DateTime, onupdate=text('CURRENT_TIMESTAMP')),
        index=True
    )
    avatar: Optional[str] = Field(sa_column=Column(TEXT))
    user_id: str = Field(max_length=32, index=True, nullable=False)
    name: str = Field(
        index=True, 
        min_length=1, 
        max_length=128,
        description='知识库名，最少1个字符，最多128个字符'
    )
    language: Optional[str] = Field(max_length=32, index=True)
    description: Optional[str] = Field(sa_column=Column(TEXT), index=True)
    embd_id: str = Field(max_length=128, nullable=False, index=True)
    permission: str = Field(
        max_length=16, 
        nullable=False,
        description='访问权限控制'
    )
    created_by: str = Field(max_length=32, nullable=False, index=True)
    doc_num: int = Field(nullable=False, index=True)
    token_num: int = Field(nullable=False, index=True)
    chunk_num: int = Field(nullable=False, index=True)
    similarity_threshold: float = Field(nullable=False)
    vector_similarity_weight: float = Field(nullable=False)
    parser_id: str = Field(max_length=32, nullable=False, index=True)
    parser_config: str = Field(sa_column=Column(TEXT), nullable=False)
    pagerank: int = Field(nullable=False)
    status: Optional[str] = Field(max_length=1, index=True)
    
    # 新增字段处理
    type: int = Field(
        default=0,
        description='0 为普通知识库，1 为QA知识库',
        sa_column_kwargs={'server_default': '0'}
    )
    model: Optional[str] = Field(description='使用的模型')
    collection_name: Optional[str] = Field(description='向量集合名称')
    index_name: Optional[str] = Field(description='索引名称')
    state: int = Field(
        default=1,
        description='0 未发布，1 已发布，2 复制中',
        sa_column_kwargs={'server_default': '1'}
    )