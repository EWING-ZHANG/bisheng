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


#bisheng的依赖
from bisheng.database.models.knowledge import (KnowledgeCreate, 
                                                KnowledgeTypeEnum)
from bisheng.database.models.user import UserDao

from bisheng.api.services.knowledge import KnowledgeService

router = APIRouter(prefix='/kb', tags=['kb_app'])
@router.post('/create', status_code=200)
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
    # dataset_name = duplicate_name(
    #     KnowledgebaseService.query,
    #     name=dataset_name,
    #     tenant_id=login_user.user_id,
    #     status=StatusEnum.VALID.value)
        
    knowledge = KnowledgeCreate(model=4,name=name,description=req.get("description", ""),type=KnowledgeTypeEnum.NORMAL.value)
    db_knowledge = KnowledgeService.create_knowledge(request, login_user, knowledge)
    try:
        # tenants = UserTenantService.query(user_id=login_user.user_id)
        req["id"] = db_knowledge.id
        req["tenant_id"] = "1"
        req["created_by"] = login_user.user_id
        req["name"] = db_knowledge.name
        # 得到固定的tenant相关的东西
        e, t = TenantService.get_by_id("1")
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
async def list_kbs(request: Request,
    keywords: Optional[str] = Query(default=""),
    page_number: int = Query(default=1, alias="page"),
    items_per_page: int = Query(default=150, alias="page_size"),
    orderby: str = Query(default="create_time", alias="orderby"),
    desc: bool = Query(default=True),
    login_user: UserPayload = Depends(get_login_user)  # 认证依赖注入[1][4]
):
        # usertenant表中获取信息
        tenants =[{"tenant_id":login_user.user_id}] # 类似java中的list列表 然后每个对象就是里面的字典
        try:
            # # 获取ragflow的所有知识库
            # kbs, total = KnowledgebaseService.get_by_tenant_ids(
            #     [m["tenant_id"] for m in tenants], login_user.user_id, 1, 100, orderby, desc, keywords)
            
            # # bisheng里面去查询用户的数据 然后对ragflow的进行过滤
            # res, total = KnowledgeService.get_knowledge(request,login_user, KnowledgeTypeEnum.NORMAL, keywords,
            #                                 page_number, items_per_page)
            # # 根据res里面的每个对象的id字段过滤调kbs里面的list对象,留下来的kbs里面的list的对象添加一个type字段为res里面对应id的type

            # return get_json_result(data={"kbs": kbs, "total": total})

            # 获取ragflow的所有知识库 
            kbs, total = KnowledgebaseService.get_by_tenant_ids(
                ["1"], 1, 1, 200, orderby, desc, '')

            # 查询Bisheng
            res, res_total = KnowledgeService.get_knowledge(request, login_user, KnowledgeTypeEnum.NORMAL, keywords,
                                                    page_number, items_per_page)
            temp = []
            result = {item["id"]: item for item in kbs}
            for item in res:
                id= str(item.id)
                if result.get(id):
                    temp.append(result.get(id))
            

            return get_json_result(data={"kbs": temp, "total": res_total})

        except Exception as e:
            return server_error_response(e)
@router.get('/rm', status_code=200)
def rm(request: Request,
        kb_id:str,
        login_user: UserPayload = Depends(get_login_user)):
    # if not KnowledgebaseService.accessible4deletion(kb_id, login_user.user_id):
    #     return get_json_result(
    #         data=False,
    #         message='No authorization.',
    #         code=settings.RetCode.AUTHENTICATION_ERROR
    #     )
    try:
        kbs = KnowledgebaseService.query(
        created_by=login_user.user_id, id=kb_id)
        if not kbs:
            return get_json_result(
                data=False, message='Only owner of knowledgebase authorized for this operation.',
                code=settings.RetCode.OPERATING_ERROR)

        for doc in DocumentService.query(kb_id):
            #  if not DocumentService.remove_document(doc, kbs[0].tenant_id):
            if not DocumentService.remove_document(doc):
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
            settings.docStoreConn.delete({"kb_id": kb.id}, search.index_name_by_kb(kb.id), kb.id)
            settings.docStoreConn.deleteIdx(search.index_name_by_kb(kb.id), kb.id)
        # 删除 bisheng里面的知识库
        from bisheng.database.models.knowledge import KnowledgeDao
        KnowledgeDao.delete_kb_mysql(kb_id)
        return get_json_result(data=True)
    except Exception as e:
        return server_error_response(e)
@router.post('/update', status_code=200)
def update(req: KnowledgeUpdateRequest,
           login_user: UserPayload = Depends(get_login_user)):
    req = req.dict()
    req["name"] = req["name"].strip()
    # if not KnowledgebaseService.accessible4deletion(req["kb_id"], login_user.user_id):
    #     return get_json_result(
    #         data=False,
    #         message='No authorization.',
    #         code=settings.RetCode.AUTHENTICATION_ERROR
    #     )
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



