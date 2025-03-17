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
from bisheng.api.db.db_models import DB,ChunkBase,ChuankRequestModel,SwitchRequest,CreateChunkModel,RetrievalRequestModel
from bisheng.api.services.user_service import UserPayload, get_login_user
import time

router = APIRouter(prefix='/chunk', tags=['ragchunk_app'])

@router.post('/list', status_code=200)
def list_chunk(req: ChunkBase=Body(...),
             login_user: UserPayload = Depends(get_login_user)): # 认证依赖注入[1][4]
    doc_id = req.doc_id
    page = req.page
    size = req.size
    question = req.keywords
    try:
        e, doc = DocumentService.get_by_id(doc_id)
        if not e:
            return get_data_error_result(message="Document not found!")
        kb_ids = KnowledgebaseService.get_kb_ids(login_user.user_id)
        query = {
            "doc_ids": [doc_id], "page": page, "size": size, "question": question, "sort": True
        }
        if req.available_int is not None:
            query["available_int"] = req.available_int
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
@router.get('/get',status_code=200)
def get(
    chunk_id:str,
    login_user: UserPayload = Depends(get_login_user)):
    try:
        tenant_id=login_user.user_id

        kb_ids = KnowledgebaseService.get_kb_ids(tenant_id)
        chunk = settings.docStoreConn.get(chunk_id, search.index_name(tenant_id), kb_ids)
        if chunk is None:
            return server_error_response(Exception("Chunk not found"))
        k = []
        for n in chunk.keys():
            if re.search(r"(_vec$|_sm_|_tks|_ltks)", n):
                k.append(n)
        for n in k:
            del chunk[n]

        return get_json_result(data=chunk)
    except Exception as e:
        if str(e).find("NotFoundError") >= 0:
            return get_json_result(data=False, message='Chunk not found!',
                                   code=settings.RetCode.DATA_ERROR)
        return server_error_response(e)

@router.post('/set',status_code=200)
def set(req: ChuankRequestModel,
        login_user: UserPayload = Depends(get_login_user)):
    d = {
        "id": req.chunk_id,  # 修改为属性访问
        "content_with_weight": req.content_with_weight  # 修改为属性访问
    }
    d["content_ltks"] = rag_tokenizer.tokenize(req.content_with_weight)
    d["content_sm_ltks"] = rag_tokenizer.fine_grained_tokenize(d["content_ltks"])
    d["important_kwd"] = req.important_kwd  # 修改为属性访问
    d["important_tks"] = rag_tokenizer.tokenize(" ".join(req.important_kwd))
    d["question_kwd"] = req.question_kwd  # 修改为属性访问
    d["question_tks"] = rag_tokenizer.tokenize("\n".join(req.question_kwd))
    
    # 修改字典键存在性检查为对象属性检查
    if hasattr(req, 'available_int'):  # 替换原来的 "available_int" in req
        d["available_int"] = req.available_int

    try:
        # 修改所有req[...]为属性访问
        tenant_id = DocumentService.get_tenant_id(req.doc_id)
        if not tenant_id:
            return get_data_error_result(message="Tenant not found!")

        embd_id = DocumentService.get_embd_id(req.doc_id)
        embd_mdl = LLMBundle(tenant_id, LLMType.EMBEDDING, embd_id)

        e, doc = DocumentService.get_by_id(req.doc_id)
        if not e:
            return get_data_error_result(message="Document not found!")

        if doc.parser_id == ParserType.QA:
            arr = [
                t for t in re.split(
                    r"[\n\t]",
                    req.content_with_weight) if len(t) > 1]
            if len(arr) != 2:
                return get_data_error_result(
                    message="Q&A must be separated by TAB/ENTER key.")
            q, a = rmPrefix(arr[0]), rmPrefix(arr[1])
            d = beAdoc(d, arr[0], arr[1], not any(
                [rag_tokenizer.is_chinese(t) for t in q + a]))

        # 修改条件表达式中的属性访问
        encode_content = req.content_with_weight if not d["question_kwd"] else "\n".join(d["question_kwd"])
        v, c = embd_mdl.encode([doc.name, encode_content])
        v = 0.1 * v[0] + 0.9 * v[1] if doc.parser_id != ParserType.QA else v[1]
        d[f"q_{len(v)}_vec"] = v.tolist()  # 改用f-string优化
        
        # 修改最后的字典访问
        settings.docStoreConn.update(
            {"id": req.chunk_id},  # 属性访问
            d, 
            search.index_name(tenant_id), 
            doc.kb_id
        )
        return get_json_result(data=True)
    except Exception as e:
        return server_error_response(e)

@router.post('/switch',status_code=200)
def switch(req: SwitchRequest,
           login_user: UserPayload = Depends(get_login_user)):
    try:
        e, doc = DocumentService.get_by_id(req.doc_id)
        if not e:
            return get_data_error_result(message="Document not found!")
        for cid in req.chunk_ids:
            if not settings.docStoreConn.update({"id": cid},
                                                {"available_int": int(req.available_int)},
                                                search.index_name(DocumentService.get_tenant_id(req.doc_id)),
                                                doc.kb_id):
                return get_data_error_result(message="Index updating failure")

            time.sleep(1)  # 根据需要调整等待时间

        return get_json_result(data=True)
    except Exception as e:
        return server_error_response(e)
@router.post('/rm',status_code=200)
def rm(req: SwitchRequest,
           login_user: UserPayload = Depends(get_login_user)):
        try:
            e, doc = DocumentService.get_by_id(req.doc_id)
            if not e:
                return get_data_error_result(message="Document not found!")
            if not settings.docStoreConn.delete({"id": req.chunk_ids}, search.index_name(login_user.user_id), doc.kb_id):
                return get_data_error_result(message="Index updating failure")
            deleted_chunk_ids = req.chunk_ids
            chunk_number = len(deleted_chunk_ids)
            DocumentService.decrement_chunk_num(doc.id, doc.kb_id, 1, chunk_number, 0)
            return get_json_result(data=True)
        except Exception as e:
            return server_error_response(e)
@router.post('/create',status_code=200)
def create(req: CreateChunkModel):
    md5 = hashlib.md5()
    md5.update((req.content_with_weight + req.doc_id).encode("utf-8"))
    chunck_id = md5.hexdigest()
    d = {
        "id": chunck_id,
        "content_ltks": rag_tokenizer.tokenize(req.content_with_weight),
        "content_with_weight": req.content_with_weight
    }
    d["content_sm_ltks"] = rag_tokenizer.fine_grained_tokenize(d["content_ltks"])
    d["important_kwd"] = req.important_kwd
    d["important_tks"] = rag_tokenizer.tokenize(" ".join(req.important_kwd))
    d["question_kwd"] = req.question_kwd
    d["question_tks"] = rag_tokenizer.tokenize("\n".join(req.question_kwd))
    d["create_time"] = str(datetime.datetime.now()).replace("T", " ")[:19]
    d["create_timestamp_flt"] = datetime.datetime.now().timestamp()

    try:
        e, doc = DocumentService.get_by_id(req.doc_id)
        if not e:
            return get_data_error_result(message="Document not found!")
        d["kb_id"] = [doc.kb_id]
        d["docnm_kwd"] = doc.name
        d["title_tks"] = rag_tokenizer.tokenize(doc.name)
        d["doc_id"] = doc.id

        tenant_id = DocumentService.get_tenant_id(req.doc_id)
        if not tenant_id:
            return get_data_error_result(message="Tenant not found!")

        e, kb = KnowledgebaseService.get_by_id(doc.kb_id)
        if not e:
            return get_data_error_result(message="Knowledgebase not found!")
        if kb.pagerank:
            d["pagerank_fea"] = kb.pagerank

        embd_id = DocumentService.get_embd_id(req.doc_id)
        embd_mdl = LLMBundle(tenant_id, LLMType.EMBEDDING.value, embd_id)

        v, c = embd_mdl.encode([doc.name, req.content_with_weight if not d["question_kwd"] else "\n".join(d["question_kwd"])])
        v = 0.1 * v[0] + 0.9 * v[1]
        d["q_%d_vec" % len(v)] = v.tolist()
        settings.docStoreConn.insert([d], search.index_name(tenant_id), doc.kb_id)

        DocumentService.increment_chunk_num(doc.id, doc.kb_id, c, 1, 0)
        return get_json_result(data={"chunk_id": chunck_id})
    except Exception as e:
        return server_error_response(e)
@router.post('/retrieval_test',status_code=200)
def retrieval_test(req: RetrievalRequestModel,
                    login_user: UserPayload = Depends(get_login_user)):
    page = req.page
    size = req.size
    question = req.question
    kb_ids = req.kb_id
    doc_ids = req.doc_ids
    similarity_threshold = req.similarity_threshold
    vector_similarity_weight = req.vector_similarity_weight
    top = req.top_k
    tenant_ids = []

    try:
        # 先不做判断
        # tenants = UserTenantService.query(user_id=login_user.user_id)
        # for kb_id in kb_ids:
        #     for tenant in tenants:
        #         if KnowledgebaseService.query(
        #                 tenant_id=tenant.tenant_id, id=kb_id):
        #             tenant_ids.append(tenant.tenant_id)
        #             break
        #     else:
        #         return {"data": False, "message": 'Only owner of knowledgebase authorized for this operation.',
        #                 "code": settings.RetCode.OPERATING_ERROR}

        e, kb = KnowledgebaseService.get_by_id(kb_ids[0])
        if not e:
            raise HTTPException(status_code=404, detail="Knowledgebase not found!")

        embd_mdl = LLMBundle(kb.tenant_id, LLMType.EMBEDDING.value, llm_name=kb.embd_id)

        rerank_mdl = None
        if req.rerank_id:
            rerank_mdl = LLMBundle(kb.tenant_id, LLMType.RERANK.value, llm_name=req.rerank_id)

        if req.keyword:
            chat_mdl = LLMBundle(kb.tenant_id, LLMType.CHAT)
            question += keyword_extraction(chat_mdl, question)

        retr = settings.retrievaler if kb.parser_id != ParserType.KG else settings.kg_retrievaler
        ranks = retr.retrieval(question, embd_mdl, tenant_ids, kb_ids, page, size,
                               similarity_threshold, vector_similarity_weight, top,
                               doc_ids, rerank_mdl=rerank_mdl, highlight=req.highlight)
        for c in ranks["chunks"]:
            c.pop("vector", None)

        return {"data": ranks}
    except Exception as e:
        if "not_found" in str(e):
            return {"data": False, "message": 'No chunk found! Check the chunk status please!',
                    "code": settings.RetCode.DATA_ERROR}
        raise HTTPException(status_code=500, detail=str(e))