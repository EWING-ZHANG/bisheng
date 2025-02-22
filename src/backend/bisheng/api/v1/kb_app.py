from fastapi import (APIRouter, BackgroundTasks, Body, Depends, File, HTTPException, Query, Request,
                     UploadFile)
from bisheng.api.services.user_service import UserPayload, get_login_user
from bisheng.api.v1.schemas import (KnowledgeFileProcess, PreviewFileChunk, UnifiedResponseModel,
                                    UpdatePreviewFileChunk, UploadFileResponse, resp_200, resp_500)
from bisheng.database.models import KnowledgeBaseBase
from bisheng.api.services.knowledge_base import KnowledgeBaseService
from bisheng.api.utils import get_data_error_result
router = APIRouter(prefix='/kb', tags=['kb'])
@router.post('/create', status_code=201)
def create_knowledge(*,
                     request: Request,
                     login_user: UserPayload = Depends(get_login_user),
                     knowledge: KnowledgeBaseBase):
    """ 创建知识库. """
    req = request.json
    dataset_name = req["name"]
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
        tenant_id=current_user.id,
        status=StatusEnum.VALID.value)
    try:
        req["id"] = get_uuid()
        req["tenant_id"] = current_user.id
        req["created_by"] = current_user.id
        e, t = TenantService.get_by_id(current_user.id)
        if not e:
            return get_data_error_result(message="Tenant not found.")
        req["embd_id"] = t.embd_id
        if not KnowledgebaseService.save(**req):
            return get_data_error_result()
        return get_json_result(data={"kb_id": req["id"]})
    except Exception as e:
        return server_error_response(e)
def duplicate_name(query_func, **kwargs):
    fnm = kwargs["name"]
    objs = query_func(**kwargs)
    if not objs: return fnm
    ext = pathlib.Path(fnm).suffix #.jpg
    nm = re.sub(r"%s$"%ext, "", fnm)
    r = re.search(r"\(([0-9]+)\)$", nm)
    c = 0
    if r:
        c = int(r.group(1))
        nm = re.sub(r"\([0-9]+\)$", "", nm)
    c += 1
    nm = f"{nm}({c})"
    if ext: nm += f"{ext}"

    kwargs["name"] = nm
    return duplicate_name(query_func, **kwargs)