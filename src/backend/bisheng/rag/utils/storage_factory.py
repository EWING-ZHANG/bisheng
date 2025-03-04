import os
from enum import Enum

from bisheng.rag.utils.azure_sas_conn import RAGFlowAzureSasBlob
from bisheng.rag.utils.azure_spn_conn import RAGFlowAzureSpnBlob
from bisheng.rag.utils.minio_conn import RAGFlowMinio
from bisheng.rag.utils.s3_conn import RAGFlowS3


class Storage(Enum):
    MINIO = 1
    AZURE_SPN = 2
    AZURE_SAS = 3
    AWS_S3 = 4


class StorageFactory:
    storage_mapping = {
        Storage.MINIO: RAGFlowMinio,
        Storage.AZURE_SPN: RAGFlowAzureSpnBlob,
        Storage.AZURE_SAS: RAGFlowAzureSasBlob,
        Storage.AWS_S3: RAGFlowS3,
    }

    @classmethod
    def create(cls, storage: Storage):
        return cls.storage_mapping[storage]()


STORAGE_IMPL_TYPE = os.getenv('STORAGE_IMPL', 'MINIO')
STORAGE_IMPL = StorageFactory.create(Storage[STORAGE_IMPL_TYPE])
