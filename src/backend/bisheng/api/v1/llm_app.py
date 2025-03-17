from fastapi import APIRouter,Depends
from bisheng.api.services.llm_service import LLMFactoriesService, TenantLLMService, LLMService
from bisheng.api.util.api_utils import get_data_error_result,get_json_result,server_error_response
from bisheng.api.db import StatusEnum, LLMType
from bisheng.api.services.user_service import UserPayload, get_login_user
from bisheng.api import settings
from typing import Optional

router = APIRouter(prefix='/llm', tags=['llm_app'])
@router.get('/list',status_code=200)
def list_app(model_type:Optional[str] = None,
            login_user: UserPayload = Depends(get_login_user)):
    self_deploied = ["Youdao", "FastEmbed", "BAAI", "Ollama", "Xinference", "LocalAI", "LM-Studio"]
    weighted = ["Youdao", "FastEmbed", "BAAI"] if settings.LIGHTEN != 0 else []
    try:
        objs = TenantLLMService.query(tenant_id=login_user.user_id)
        facts = set([o.to_dict()["llm_factory"] for o in objs if o.api_key])
        llms = LLMService.get_all()
        llms = [m.to_dict()
                for m in llms if m.status == StatusEnum.VALID.value and m.fid not in weighted]
        for m in llms:
            m["available"] = m["fid"] in facts or m["llm_name"].lower() == "flag-embedding" or m["fid"] in self_deploied

        llm_set = set([m["llm_name"] + "@" + m["fid"] for m in llms])
        for o in objs:
            if not o.api_key: continue
            if o.llm_name + "@" + o.llm_factory in llm_set: continue
            llms.append({"llm_name": o.llm_name, "model_type": o.model_type, "fid": o.llm_factory, "available": True})

        res = {}
        for m in llms:
            if model_type and m["model_type"].find(model_type) < 0:
                continue
            if m["fid"] not in res:
                res[m["fid"]] = []
            res[m["fid"]].append(m)

        return get_json_result(data=res)
    except Exception as e:
        return server_error_response(e)

