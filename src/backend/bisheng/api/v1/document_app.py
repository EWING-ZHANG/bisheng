from fastapi import (APIRouter, BackgroundTasks, Body, Depends, File, HTTPException, Query, Request,Response,
                     UploadFile)
from bisheng.api.services.user_service import UserPayload, get_login_user
from bisheng.api.util.api_utils import get_data_error_result,get_json_result,server_error_response
from bisheng.api.services.knowledgebase_service import KnowledgebaseService 
from bisheng.api import settings
from typing import Dict, List, Optional
from bisheng.api.services.document_service import DocumentService
from bisheng.api.constants import IMG_BASE64_PREFIX
from fastapi.responses import JSONResponse
from fastapi import Form
from fastapi.responses import StreamingResponse  # 新增StreamingResponse

from bisheng.api.services.file_service import FileService
from bisheng.api.db.db_models import DB,Task,ChangeParserRequest,ParseRun,ChunkBase,DocStatus,docRm
from bisheng.api.util import get_uuid
from bisheng.api.db import FileType, TaskStatus, ParserType, FileSource
from bisheng.rag.nlp import search
from bisheng.api.services.file2document_service import File2DocumentService
from bisheng.rag.utils.storage_factory import STORAGE_IMPL
import pathlib
import re
import mimetypes
from bisheng.api.services.task_service import TaskService, queue_tasks
from fastapi import File, UploadFile
from urllib.parse import quote  # 新增引用


router = APIRouter(prefix='/document', tags=['document_app'])
@router.get('/list')
def list_docs(kb_id: str,
                keywords: Optional[str] = Query(default=""),
                page_number: int = Query(default=1, alias="page"),
                items_per_page: int = Query(default=150, alias="page_size"),
                orderby: str = Query(default="create_time", alias="orderby"),
                desc: bool = Query(default=True),
                login_user: UserPayload = Depends(get_login_user)):
    if not kb_id:
        return get_json_result(
            data=False, message='Lack of "KB ID"', code=settings.RetCode.ARGUMENT_ERROR)
    if not KnowledgebaseService.query(
            tenant_id=login_user.user_id, id=kb_id):
        return get_json_result(
            data=False, message='Only owner of knowledgebase authorized for this operation.',
            code=settings.RetCode.OPERATING_ERROR)
    try:
        docs, tol = DocumentService.get_by_kb_id(
            kb_id, page_number, items_per_page, orderby, desc, keywords)

        for doc_item in docs:
            if doc_item['thumbnail'] and not doc_item['thumbnail'].startswith(IMG_BASE64_PREFIX):
                doc_item['thumbnail'] = f"/v1/document/image/{kb_id}-{doc_item['thumbnail']}"

        return get_json_result(data={"total": tol, "docs": docs})
    except Exception as e:
        return server_error_response(e)
@router.post("/upload",status_code=200)
async def upload(
    kb_id: str = Form(...),
    files: List[UploadFile] = File(...),
    login_user: UserPayload = Depends(get_login_user)):
    # Validate kb_id
    if not kb_id:
        return JSONResponse(
            status_code=400,
            content={
                "data": False,
                "message": 'Lack of "KB ID"',
                "code": settings.RetCode.ARGUMENT_ERROR
            }
        )
    
    # Check if files were provided
    if not files:
        return JSONResponse(
            status_code=400,
            content={
                "data": False,
                "message": 'No file part!',
                "code": settings.RetCode.ARGUMENT_ERROR
            }
        )

    for file_obj in files:
        if file_obj.filename == '':
            return get_json_result(
                data=False, message='No file selected!', code=settings.RetCode.ARGUMENT_ERROR)

    e, kb = KnowledgebaseService.get_by_id(kb_id)
    if not e:
        raise LookupError("Can't find this knowledgebase!")
    with DB.connection_context():  # 确保连接在请求结束后关闭
        err, _ = await FileService.upload_document(kb, files, login_user.user_id)
    if err:
        return get_json_result(
            data=False, message="\n".join(err), code=settings.RetCode.SERVER_ERROR)
    return get_json_result(data=True)
@router.post('/create',status_code=200)
def create(kb_id:str,
           name:str,
            login_user: UserPayload = Depends(get_login_user)  # 认证依赖注入[1][4]
           ):
    if not kb_id:
        return get_json_result(
            data=False, message='Lack of "KB ID"', code=settings.RetCode.ARGUMENT_ERROR)

    try:
        e, kb = KnowledgebaseService.get_by_id(kb_id)
        if not e:
            return get_data_error_result(
                message="Can't find this knowledgebase!")
        res = DocumentService.query(name, kb_id)
        if len(res)!=0:
            return get_data_error_result(
                message="Duplicated document name in the same knowledgebase.")

        doc = DocumentService.insert({
            "id": get_uuid(),
            "kb_id": kb.id,
            "parser_id": kb.parser_id,
            "parser_config": kb.parser_config,
            "created_by": login_user.user_id,
            "type": FileType.VIRTUAL,
            "name": name,
            "location": "",
            "size": 0
        })
        return get_json_result(data=doc)
    except Exception as e:
        return server_error_response(e)
@router.post('/infos',status_code=200)
def docinfos(doc_ids: List[str] =Body(...,alias="doc_ids"),
             login_user: UserPayload = Depends(get_login_user)  # 认证依赖注入[1][4]
             ):
    for doc_id in doc_ids:
        if not DocumentService.accessible(doc_id, login_user.user_id):
            return get_json_result(
                data=False,
                message='No authorization.',
                code=settings.RetCode.AUTHENTICATION_ERROR
            )
    docs = DocumentService.get_by_ids(doc_ids)
    return get_json_result(data=list(docs.dicts()))

@router.get('/thumbnails')
def thumbnails(doc_ids:str,
               login_user: UserPayload = Depends(get_login_user)  # 认证依赖注入[1][4]
               ):
    doc_ids = doc_ids.split(",")
    if not doc_ids:
        return get_json_result(
            data=False, message='Lack of "Document ID"', code=settings.RetCode.ARGUMENT_ERROR)

    try:
        docs = DocumentService.get_thumbnails(doc_ids)

        for doc_item in docs:
            if doc_item['thumbnail'] and not doc_item['thumbnail'].startswith(IMG_BASE64_PREFIX):
                doc_item['thumbnail'] = f"/v1/document/image/{doc_item['kb_id']}-{doc_item['thumbnail']}"

        return get_json_result(data={d["id"]: d["thumbnail"] for d in docs})
    except Exception as e:
        return server_error_response(e)
@router.post('/change_status',status_code=200)
def change_status(req: DocStatus,
                login_user: UserPayload = Depends(get_login_user)  # 认证依赖注入[1][4]
):
    status=req.status
    doc_id=req.doc_id
    if str(status) not in ["0", "1"]:
        return get_json_result(
            data=False,
            message='"Status" must be either 0 or 1!',
            code=settings.RetCode.ARGUMENT_ERROR)

    if not DocumentService.accessible(doc_id, login_user.user_id):
        return get_json_result(
            data=False,
            message='No authorization.',
            code=settings.RetCode.AUTHENTICATION_ERROR)

    try:
        e, doc = DocumentService.get_by_id(doc_id)
        if not e:
            return get_data_error_result(message="Document not found!")
        e, kb = KnowledgebaseService.get_by_id(doc.kb_id)
        if not e:
            return get_data_error_result(
                message="Can't find this knowledgebase!")

        if not DocumentService.update_by_id(
                doc_id, {"status": str(status)}):
            return get_data_error_result(
                message="Database error (Document update)!")

        status = int(status)
        settings.docStoreConn.update({"doc_id": doc_id}, {"available_int": status},
                                     search.index_name(kb.tenant_id), doc.kb_id)
        return get_json_result(data=True)
    except Exception as e:
        return server_error_response(e)   
@router.post('/rm')
def rm(doc_ids:docRm,
        login_user: UserPayload = Depends(get_login_user)):
    # if isinstance(doc_id, str): doc_ids = [doc_id]
    doc_ids = doc_ids.doc_ids
    for doc_id in doc_ids:
        if not DocumentService.accessible4deletion(doc_id, login_user.user_id):
            return get_json_result(
                data=False,
                message='No authorization.',
                code=settings.RetCode.AUTHENTICATION_ERROR
            )

    root_folder = FileService.get_root_folder(login_user.user_id)
    pf_id = root_folder["id"]
    FileService.init_knowledgebase_docs(pf_id, login_user.user_id)
    errors = ""
    for doc_id in doc_ids:
        try:
            e, doc = DocumentService.get_by_id(doc_id)
            if not e:
                return get_data_error_result(message="Document not found!")
            tenant_id = DocumentService.get_tenant_id(doc_id)
            if not tenant_id:
                return get_data_error_result(message="Tenant not found!")

            b, n = File2DocumentService.get_storage_address(doc_id=doc_id)

            if not DocumentService.remove_document(doc, tenant_id):
                return get_data_error_result(
                    message="Database error (Document removal)!")

            # f2d = File2DocumentService.get_by_document_id(doc_id)
            # FileService.filter_delete([File.source_type == FileSource.KNOWLEDGEBASE, File.id == f2d[0].file_id])
            File2DocumentService.delete_by_document_id(doc_id)

            STORAGE_IMPL.rm(b, n)
        except Exception as e:
            errors += str(e)

    if errors:
        return get_json_result(data=False, message=errors, code=settings.RetCode.SERVER_ERROR)
 
    return get_json_result(data=True)
@router.get('/rename',status_code=200)
def rename(doc_id:str,
           name: str,
           login_user: UserPayload = Depends(get_login_user)):
    if not DocumentService.accessible(doc_id, login_user.user_id):
        return get_json_result(
            data=False,
            message='No authorization.',
            code=settings.RetCode.AUTHENTICATION_ERROR
        )
    try:
        e, doc = DocumentService.get_by_id(doc_id)
        if not e:
            return get_data_error_result(message="Document not found!")
        # 修改名字前后的后缀是否一致 txt 和txt
        if pathlib.Path(name.lower()).suffix != pathlib.Path(
                doc.name.lower()).suffix:
            return get_json_result(
                data=False,
                message="The extension of file can't be changed",
                code=settings.RetCode.ARGUMENT_ERROR)
        for d in DocumentService.query(name, kb_id=doc.kb_id):
            if d.name == name:
                return get_data_error_result(
                    message="Duplicated document name in the same knowledgebase.")

        if not DocumentService.update_by_id(
                doc_id, {"name": name}):
            return get_data_error_result(
                message="Database error (Document rename)!")

        informs = File2DocumentService.get_by_document_id(doc_id)
        if informs:
            e, file = FileService.get_by_id(informs[0].file_id)
            FileService.update_by_id(file.id, {"name": name})

        return get_json_result(data=True)
    except Exception as e:
        return server_error_response(e)
@router.get('/get/{doc_id}',status_code=200)
async def get_document(doc_id: str) -> Response:
    try:
        # 获取文档元数据
        exists, doc = DocumentService.get_by_id(doc_id)
        if not exists:
            raise HTTPException(status_code=404, detail="Document not found")

        # 获取存储位置信息
        bucket_name, object_name = File2DocumentService.get_storage_address(doc_id=doc_id)
        
        # 使用原有的同步get方法获取字节数据
        file_bytes = STORAGE_IMPL.get(bucket_name, object_name)  # 确保返回bytes类型
        
        # 精确识别MIME类型
        mime_type, _ = mimetypes.guess_type(doc.name)
        if not mime_type:
            # 根据文档类型回退
            mime_type = "image/jpeg" if doc.type == FileType.VISUAL.value else "application/octet-stream"
        
        # 处理特殊字符文件名
        safe_filename = quote(doc.name)
        content_disposition = f"inline; filename*=UTF-8''{safe_filename}"

        return Response(
            content=file_bytes,
            media_type=mime_type,
            headers={
                "Content-Disposition": content_disposition,
                "Content-Length": str(len(file_bytes))  # 添加实际内容长度
            }
        )
    
    except Exception as e:
        # 细化错误处理
        if isinstance(e, AttributeError) and "'get'" in str(e):
            raise HTTPException(
                status_code=500,
                detail="Storage service configuration error"
            )
        elif isinstance(e, ConnectionError):
            raise HTTPException(
                status_code=503,
                detail="Storage service unavailable"
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Document retrieval failed: {str(e)}"
            )
@router.get('/image/{image_id}', status_code=200)
def get_image(image_id: str):
    try:
        # 拆分存储地址和文件名
        bkt, nm = image_id.split("-")
        
        # 获取二进制数据
        file_data = STORAGE_IMPL.get(bkt, nm)
        
        # 构造FastAPI响应对象
        response = Response(content=file_data)
        
        # 动态设置Content-Type
        if '.' in nm:  # 从文件名提取扩展名
            file_ext = re.search(r'\.([^.]+)$', nm).group(1).lower()
            mime_type = f'image/{file_ext}' if file_ext in ['jpeg', 'png', 'gif'] else 'application/octet-stream'
        else:
            mime_type, _ = mimetypes.guess_type(nm)
        
        response.headers['Content-Type'] = mime_type or 'application/octet-stream'
        
        return response
    except ValueError:
        return server_error_response("Invalid image_id format")
    except Exception as e:
        return server_error_response(str(e))
    
@router.post('/change_parser',status_code=200)
def change_parser(req: ChangeParserRequest = Body(...),
                  login_user: UserPayload = Depends(get_login_user)):

    if not DocumentService.accessible(req.doc_id, login_user.user_id):
        return get_json_result(
            data=False,
            message='No authorization.',
            code=settings.RetCode.AUTHENTICATION_ERROR
        )
    try:
        e, doc = DocumentService.get_by_id(req.doc_id)
        if not e:
            return get_data_error_result(message="Document not found!")
        if doc.parser_id.lower() == req.parser_id.lower():
            if hasattr(req, 'parser_config'):
                if req.parser_config == doc.parser_config:
                    return get_json_result(data=True)
            else:
                return get_json_result(data=True)

        if ((doc.type == FileType.VISUAL and req.parser_id != "picture")
                or (re.search(
                    r"\.(ppt|pptx|pages)$", doc.name) and req.parser_id != "presentation")):
            return get_data_error_result(message="Not supported yet!")

        e = DocumentService.update_by_id(doc.id,
                                         {"parser_id": req.parser_id, "progress": 0, "progress_msg": "",
                                          "run": TaskStatus.UNSTART.value})
        if not e:
            return get_data_error_result(message="Document not found!")
        if hasattr(req, 'parser_config'):
            DocumentService.update_parser_config(doc.id, req.parser_config)
        if doc.token_num > 0:
            e = DocumentService.increment_chunk_num(doc.id, doc.kb_id, doc.token_num * -1, doc.chunk_num * -1,
                                                    doc.process_duation * -1)
            if not e:
                return get_data_error_result(message="Document not found!")
            tenant_id = DocumentService.get_tenant_id(req.doc_id)
            if not tenant_id:
                return get_data_error_result(message="Tenant not found!")
            if settings.docStoreConn.indexExist(search.index_name(tenant_id), doc.kb_id):
                settings.docStoreConn.delete({"doc_id": doc.id}, search.index_name(tenant_id), doc.kb_id)

        return get_json_result(data=True)
    except Exception as e:
        return server_error_response(e)
@router.post('/run',status_code=200)
def run(req: ParseRun=Body(...),
        login_user: UserPayload = Depends(get_login_user)):
    for doc_id in req.doc_ids:
        if not DocumentService.accessible(doc_id, login_user.user_id):
            return get_json_result(
                data=False,
                message='No authorization.',
                code=settings.RetCode.AUTHENTICATION_ERROR
            )
    try:
        for id in req.doc_ids:
            info = {"run": str(req.run), "progress": 0}
            if str(req.run) == TaskStatus.RUNNING.value:
                info["progress_msg"] = ""
                info["chunk_num"] = 0
                info["token_num"] = 0
            DocumentService.update_by_id(id, info)
            # if str(req.run) == TaskStatus.CANCEL.value:
            tenant_id = login_user.user_id
            if not tenant_id:
                return get_data_error_result(message="Tenant not found!")
            e, doc = DocumentService.get_by_id(id)
            if not e:
                return get_data_error_result(message="Document not found!")
            if settings.docStoreConn.indexExist(search.index_name(tenant_id), doc.kb_id):
                settings.docStoreConn.delete({"doc_id": id}, search.index_name(tenant_id), doc.kb_id)

            if str(req.run) == TaskStatus.RUNNING.value:
                TaskService.filter_delete([Task.doc_id == id])
                e, doc = DocumentService.get_by_id(id)
                doc = doc.to_dict()
                doc["tenant_id"] = tenant_id
                bucket, name = File2DocumentService.get_storage_address(doc_id=doc["id"])
                queue_tasks(doc, bucket, name)

        return get_json_result(data=True)
    except Exception as e:
        return server_error_response(e)

    