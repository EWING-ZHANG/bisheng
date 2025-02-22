from bisheng.api.services.user_service import UserPayload
from fastapi import BackgroundTasks, Request
from bisheng.database.models import KnowledgeBaseBase
class KnowledgeBaseService:
    @classmethod
    def create_knowledge(cls, request: Request, login_user: UserPayload,
                         knowledge: KnowledgeBaseBase):
    