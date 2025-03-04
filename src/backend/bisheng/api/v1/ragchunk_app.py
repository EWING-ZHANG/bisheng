#
#  Copyright 2024 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
import datetime
import json

from fastapi import (APIRouter, BackgroundTasks, Body, Depends, File, HTTPException, Query, Request,
                     UploadFile)

from bisheng.services.dialog_service import keyword_extraction
from bisheng.rag.app.qa import rmPrefix, beAdoc
from bisheng.rag.nlp import search, rag_tokenizer
from bisheng.rag.utils import rmSpace
from bisheng.api.db import LLMType, ParserType
from bisheng.api.services.knowledgebase_service import KnowledgebaseService
from bisheng.api.services.llm_service import LLMBundle
from bisheng.api.util.api_utils import get_data_error_result,get_json_result,server_error_response
from bisheng.api.services.document_service import DocumentService
from bisheng.api import settings
from bisheng.api.util.api_utils import get_json_result
import hashlib
import re
from bisheng.api.db.db_models import DB,ChunkBase
from bisheng.api.services.user_service import UserPayload, get_login_user

router = APIRouter(prefix='/chunk', tags=['ragchunk_app'])

@router.post('/list', status_code=200)
def list_chunk(req: ChunkBase=Body(...),
             login_user: UserPayload = Depends(get_login_user)): # 认证依赖注入[1][4]
    doc_id = req.doc_id
    page = req.page
    size = req.size
    question = req.keywards
    try:
        e, doc = DocumentService.get_by_id(doc_id)
        if not e:
            return get_data_error_result(message="Document not found!")
        kb_ids = KnowledgebaseService.get_kb_ids(login_user.user_id)
        query = {
            "doc_ids": [doc_id], "page": page, "size": size, "question": question, "sort": True
        }
        if hasattr(req,'available_int'):
            query.available_int = req.available_int
        sres = settings.retrievaler.search(query, search.index_name(login_user.user_id), kb_ids, highlight=True)
        res = {"total": sres.total, "chunks": [], "doc": doc.to_dict()}
        for id in sres.ids:
            d = {
                "chunk_id": id,
                "content_with_weight": rmSpace(sres.highlight[id]) if question and id in sres.highlight else sres.field[
                    id].get(
                    "content_with_weight", ""),
                "doc_id": sres.field[id]["doc_id"],
                "docnm_kwd": sres.field[id]["docnm_kwd"],
                "important_kwd": sres.field[id].get("important_kwd", []),
                "question_kwd": sres.field[id].get("question_kwd", []),
                "image_id": sres.field[id].get("img_id", ""),
                "available_int": int(sres.field[id].get("available_int", 1)),
                "positions": json.loads(sres.field[id].get("position_list", "[]")),
            }
            assert isinstance(d["positions"], list)
            assert len(d["positions"]) == 0 or (isinstance(d["positions"][0], list) and len(d["positions"][0]) == 5)
            res["chunks"].append(d)
        return get_json_result(data=res)
    except Exception as e:
        if str(e).find("not_found") > 0:
            return get_json_result(data=False, message='No chunk found!',
                                   code=settings.RetCode.DATA_ERROR)
        return server_error_response(e)



