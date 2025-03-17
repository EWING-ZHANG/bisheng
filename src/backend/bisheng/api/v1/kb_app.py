from fastapi import (APIRouter, BackgroundTasks, Body, Depends, File, HTTPException, Query, Request,
                     UploadFile)
from bisheng.api.services.user_service import UserPayload, get_login_user
from bisheng.api.v1.schemas import (KnowledgeFileProcess, PreviewFileChunk, UnifiedResponseModel,
                                    UpdatePreviewFileChunk, UploadFileResponse, resp_200, resp_500)
# from bisheng.database.models import KnowledgeBaseBase
from bisheng.api.services.knowledgebase_service import KnowledgebaseService 
from bisheng.api.util.api_utils import get_data_error_result,get_json_result,server_error_response
from bisheng.api.constants import DATASET_NAME_LIMIT
from bisheng.api.services import duplicate_name
from bisheng.api.db import StatusEnum, FileSource
from bisheng.api.util import get_uuid
from bisheng.database.models.user import UserDao
from bisheng.api import settings
from typing import Dict, List, Optional
from bisheng.api.services.document_service import DocumentService
from bisheng.api.services.file2document_service import File2DocumentService
from bisheng.api.services.file_service import FileService
from bisheng.rag.nlp import search
from bisheng.api.db.db_models import File,KnowledgeUpdateRequest
from bisheng.api.services.user_service_rag import TenantService, UserTenantService
router = APIRouter(prefix='/kb', tags=['kb_app'])
@router.post('/create', status_code=201)
async def create_knowledge(*,
                     request: Request,
                     login_user: UserPayload = Depends(get_login_user),
                     name:str = Body(...,embed=True)):
    """ 创建知识库. """
    req = await request.json()  
    dataset_name = name
    if not isinstance(dataset_name, str):
        return get_data_error_result(message="Dataset name must be string.")
    if dataset_name == "":
        return get_data_error_result(message="Dataset name can't be empty.")
    if len(dataset_name) >= DATASET_NAME_LIMIT:
        return get_data_error_result(
            message=f"Dataset name length is {len(dataset_name)} which is large than {DATASET_NAME_LIMIT}")

    dataset_name = dataset_name.strip()
    dataset_name = duplicate_name(
        KnowledgebaseService.query,
        name=dataset_name,
        tenant_id=login_user.user_id,
        status=StatusEnum.VALID.value)
    try:
        req["id"] = get_uuid()
        req["tenant_id"] = login_user.user_id
        req["created_by"] = login_user.user_id
        req["name"] = dataset_name
        e, t = TenantService.get_by_id(login_user.user_id)
        if not e:
            return get_data_error_result(message="Tenant not found.")
        req["embd_id"] = t.embd_id
        if not KnowledgebaseService.save(**req):
            return get_data_error_result()
        return get_json_result(data={"kb_id": req["id"]})
    except Exception as e:
        return server_error_response(e)
@router.get('/detail', status_code=200)
async def detail(kb_id: str,login_user: UserPayload = Depends(get_login_user)):
    try:
        user = UserDao.get_user(login_user.user_id)
        if not user:
            if not KnowledgebaseService.query(
                    tenant_id=login_user.user_id, id=kb_id):
                return get_json_result(
                data=False, message='Only owner of knowledgebase authorized for this operation.',
                code="settings.RetCode.OPERATING_ERROR")

        # else:
        #     return get_json_result(
        #         data=False, message='Only owner of knowledgebase authorized for this operation.',
        #         code=settings.RetCode.OPERATING_ERROR)
        kb = KnowledgebaseService.get_detail(kb_id)
        if not kb:
            return get_data_error_result(
                message="Can't find this knowledgebase!")
        return get_json_result(data=kb)
    except Exception as e:
        return server_error_response(e)
@router.get('/list', status_code=200)
async def list_kbs(
    keywords: Optional[str] = Query(default=""),
    page_number: int = Query(default=1, alias="page"),
    items_per_page: int = Query(default=150, alias="page_size"),
    orderby: str = Query(default="create_time", alias="orderby"),
    desc: bool = Query(default=True),
    login_user: UserPayload = Depends(get_login_user)  # 认证依赖注入[1][4]
):
        tenants =[{"tenant_id":login_user.user_id}] # 类似java中的list列表 然后每个对象就是里面的字典
        try:
            kbs, total = KnowledgebaseService.get_by_tenant_ids(
                [m["tenant_id"] for m in tenants], login_user.user_id, page_number, items_per_page, orderby, desc, keywords)
            return get_json_result(data={"kbs": kbs, "total": total})
        except Exception as e:
            return server_error_response(e)
@router.get('/rm', status_code=200)
def rm(kb_id:str,
        login_user: UserPayload = Depends(get_login_user)):
    if not KnowledgebaseService.accessible4deletion(kb_id, login_user.user_id):
        return get_json_result(
            data=False,
            message='No authorization.',
            code=settings.RetCode.AUTHENTICATION_ERROR
        )
    try:
        kbs = KnowledgebaseService.query(
        created_by=login_user.user_id, id=kb_id)
        if not kbs:
            return get_json_result(
                data=False, message='Only owner of knowledgebase authorized for this operation.',
                code=settings.RetCode.OPERATING_ERROR)

        for doc in DocumentService.query(kb_id):
            if not DocumentService.remove_document(doc, kbs[0].tenant_id):
                return get_data_error_result(
                    message="Database error (Document removal)!")
            f2d = File2DocumentService.get_by_document_id(doc.id)
            FileService.filter_delete([File.source_type == FileSource.KNOWLEDGEBASE, File.id == f2d[0].file_id])
            File2DocumentService.delete_by_document_id(doc.id)
        FileService.filter_delete(
            [File.source_type == FileSource.KNOWLEDGEBASE, File.type == "folder", File.name == kbs[0].name])
        if not KnowledgebaseService.delete_by_id(kb_id):
            return get_data_error_result(
                message="Database error (Knowledgebase removal)!")
        for kb in kbs:
            settings.docStoreConn.delete({"kb_id": kb.id}, search.index_name(kb.tenant_id), kb.id)
            settings.docStoreConn.deleteIdx(search.index_name(kb.tenant_id), kb.id)
        return get_json_result(data=True)
    except Exception as e:
        return server_error_response(e)
@router.post('/update', status_code=200)
def update(req: KnowledgeUpdateRequest,
           login_user: UserPayload = Depends(get_login_user)):
    req = req.dict()
    req["name"] = req["name"].strip()
    if not KnowledgebaseService.accessible4deletion(req["kb_id"], login_user.user_id):
        return get_json_result(
            data=False,
            message='No authorization.',
            code=settings.RetCode.AUTHENTICATION_ERROR
        )
    try:
        if not KnowledgebaseService.query(
                created_by=login_user.user_id, id=req["kb_id"]):
            return get_json_result(
                data=False, message='Only owner of knowledgebase authorized for this operation.',
                code=settings.RetCode.OPERATING_ERROR)

        e, kb = KnowledgebaseService.get_by_id(req["kb_id"])
        if not e:
            return get_data_error_result(
                message="Can't find this knowledgebase!")

        if req["name"].lower() != kb.name.lower() \
                and len(
            KnowledgebaseService.query(name=req["name"], tenant_id=login_user.user_id, status=StatusEnum.VALID.value)) > 1:
            return get_data_error_result(
                message="Duplicated knowledgebase name.")

        del req["kb_id"]
        if not KnowledgebaseService.update_by_id(kb.id, req):
            return get_data_error_result()

        if kb.pagerank != req.get("pagerank", 0):
            if req.get("pagerank", 0) > 0:
                settings.docStoreConn.update({"kb_id": kb.id}, {"pagerank_fea": req["pagerank"]},
                                         search.index_name(kb.tenant_id), kb.id)
            else:
                settings.docStoreConn.update({"exist": "pagerank_fea"}, {"remove": "pagerank_fea"},
                                         search.index_name(kb.tenant_id), kb.id)

        e, kb = KnowledgebaseService.get_by_id(kb.id)
        if not e:
            return get_data_error_result(
                message="Database error (Knowledgebase rename)!")

        return get_json_result(data=kb.to_json())
    except Exception as e:
        return server_error_response(e)



