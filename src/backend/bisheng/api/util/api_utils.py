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
import logging
import functools
import json
import random
import time
from base64 import b64encode
from functools import wraps
from hmac import HMAC
from io import BytesIO
from urllib.parse import quote, urlencode
from uuid import uuid1

import requests
from fastapi import Response, Request as flask_request


from itsdangerous import URLSafeTimedSerializer
from werkzeug.http import HTTP_STATUS_CODES

from bisheng.api.db.db_models import APIToken
from bisheng.api import settings

from bisheng.api import settings
from bisheng.api.util import CustomJSONEncoder, get_uuid
from bisheng.api.util import json_dumps
from bisheng.api.constants import REQUEST_WAIT_SEC, REQUEST_MAX_WAIT_SEC

requests.models.complexjson.dumps = functools.partial(
    json.dumps, cls=CustomJSONEncoder)


def request(**kwargs):
    sess = requests.Session()
    stream = kwargs.pop('stream', sess.stream)
    timeout = kwargs.pop('timeout', None)
    kwargs['headers'] = {
        k.replace(
            '_',
            '-').upper(): v for k,
                                v in kwargs.get(
            'headers',
            {}).items()}
    prepped = requests.Request(**kwargs).prepare()

    if settings.CLIENT_AUTHENTICATION and settings.HTTP_APP_KEY and settings.SECRET_KEY:
        timestamp = str(round(time() * 1000))
        nonce = str(uuid1())
        signature = b64encode(HMAC(settings.SECRET_KEY.encode('ascii'), b'\n'.join([
            timestamp.encode('ascii'),
            nonce.encode('ascii'),
            settings.HTTP_APP_KEY.encode('ascii'),
            prepped.path_url.encode('ascii'),
            prepped.body if kwargs.get('json') else b'',
            urlencode(
                sorted(
                    kwargs['data'].items()),
                quote_via=quote,
                safe='-._~').encode('ascii')
            if kwargs.get('data') and isinstance(kwargs['data'], dict) else b'',
        ]), 'sha1').digest()).decode('ascii')

        prepped.headers.update({
            'TIMESTAMP': timestamp,
            'NONCE': nonce,
            'APP-KEY': settings.HTTP_APP_KEY,
            'SIGNATURE': signature,
        })

    return sess.send(prepped, stream=stream, timeout=timeout)


def get_exponential_backoff_interval(retries, full_jitter=False):
    """Calculate the exponential backoff wait time."""
    # Will be zero if factor equals 0
    countdown = min(REQUEST_MAX_WAIT_SEC, REQUEST_WAIT_SEC * (2 ** retries))
    # Full jitter according to
    # https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
    if full_jitter:
        countdown = random.randrange(countdown + 1)
    # Adjust according to maximum wait time and account for negative values.
    return max(0, countdown)


def get_data_error_result(code=settings.RetCode.DATA_ERROR,
                          message='Sorry! Data missing!'):
    import re
    result_dict = {
        "code": code,
        "message": re.sub(
            r"rag",
            "seceum",
            message,
            flags=re.IGNORECASE)}
    response = {}
    for key, value in result_dict.items():
        if value is None and key != "code":
            continue
        else:
            response[key] = value
    return response


def server_error_response(e):
    logging.exception(e)
    try:
        if e.code == 401:
            return get_json_result(code=401, message=repr(e))
    except BaseException:
        pass
    if len(e.args) > 1:
        return get_json_result(
            code=settings.RetCode.EXCEPTION_ERROR, message=repr(e.args[0]), data=e.args[1])
    return get_json_result(code=settings.RetCode.EXCEPTION_ERROR, message=repr(e))


def error_response(response_code, message=None):
    if message is None:
        message = HTTP_STATUS_CODES.get(response_code, 'Unknown Error')

    return Response(json.dumps({
        'message': message,
        'code': response_code,
    }), status=response_code, mimetype='application/json')


def validate_request(*args, **kwargs):
    def wrapper(func):
        @wraps(func)
        def decorated_function(*_args, **_kwargs):
            input_arguments = flask_request.json or flask_request.form.to_dict()
            no_arguments = []
            error_arguments = []
            for arg in args:
                if arg not in input_arguments:
                    no_arguments.append(arg)
            for k, v in kwargs.items():
                config_value = input_arguments.get(k, None)
                if config_value is None:
                    no_arguments.append(k)
                elif isinstance(v, (tuple, list)):
                    if config_value not in v:
                        error_arguments.append((k, set(v)))
                elif config_value != v:
                    error_arguments.append((k, v))
            if no_arguments or error_arguments:
                error_string = ""
                if no_arguments:
                    error_string += "required argument are missing: {}; ".format(
                        ",".join(no_arguments))
                if error_arguments:
                    error_string += "required argument values: {}".format(
                        ",".join(["{}={}".format(a[0], a[1]) for a in error_arguments]))
                return get_json_result(
                    code=settings.RetCode.ARGUMENT_ERROR, message=error_string)
            return func(*_args, **_kwargs)

        return decorated_function

    return wrapper

def not_allowed_parameters(*params):
    def decorator(f):
        def wrapper(*args, **kwargs):
            input_arguments = flask_request.json or flask_request.form.to_dict()
            for param in params:
                if param in input_arguments:
                    return get_json_result(
                        code=settings.RetCode.ARGUMENT_ERROR, message=f"Parameter {param} isn't allowed")
            return f(*args, **kwargs)
        return wrapper
    return decorator


def is_localhost(ip):
    return ip in {'127.0.0.1', '::1', '[::1]', 'localhost'}


# def send_file_in_mem(data, filename):
#     if not isinstance(data, (str, bytes)):
#         data = json_dumps(data)
#     if isinstance(data, str):
#         data = data.encode('utf-8')

#     f = BytesIO()
#     f.write(data)
#     f.seek(0)

#     return send_file(f, as_attachment=True, attachment_filename=filename)
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from io import BytesIO
import json
from typing import Union

router = APIRouter()

def send_file_in_mem(data: Union[str, bytes, dict, list], filename: str) -> StreamingResponse:
    """
    将内存中的数据作为文件附件返回（FastAPI 版本）
    
    Args:
        data: 要发送的数据（支持字符串、字节、字典、列表等）
        filename: 下载时的文件名（如 "data.json"）
        
    Returns:
        StreamingResponse: FastAPI 响应对象
    """
    # 将非字节/字符串数据转为 JSON 字符串，再编码为字节
    if not isinstance(data, (str, bytes)):
        data = json.dumps(data, ensure_ascii=False)
    if isinstance(data, str):
        data = data.encode("utf-8")

    # 创建内存文件对象
    file_stream = BytesIO(data)
    
    # 根据文件后缀设置 MIME 类型（可选）
    content_type = "application/octet-stream"
    if "." in filename:
        file_ext = filename.split(".")[-1].lower()
        mime_map = {
            "json": "application/json",
            "csv": "text/csv",
            "txt": "text/plain",
            "png": "image/png",
            "jpg": "image/jpeg",
        }
        content_type = mime_map.get(file_ext, content_type)

    # 构建响应头
    headers = {
        "Content-Disposition": f"attachment; filename={filename}",
        "Access-Control-Expose-Headers": "Content-Disposition"
    }

    return StreamingResponse(
        content=iter([file_stream.getvalue()]),  # 直接传递字节内容
        media_type=content_type,
        headers=headers
    )


def get_json_result(code=settings.RetCode.SUCCESS, message='success', data=None):
    response = {"code": code, "message": message, "data": data}
    return response

def apikey_required(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        token = flask_request.headers.get('Authorization').split()[1]
        objs = APIToken.query(token=token)
        if not objs:
            return build_error_result(
                message='API-KEY is invalid!', code=settings.RetCode.FORBIDDEN
            )
        kwargs['tenant_id'] = objs[0].tenant_id
        return func(*args, **kwargs)

    return decorated_function


def build_error_result(code=settings.RetCode.FORBIDDEN, message='success'):
    response = {"code": code, "message": message}
    response = response
    response.status_code = code
    return response


def construct_response(code=settings.RetCode.SUCCESS,
                       message='success', data=None, auth=None):
    result_dict = {"code": code, "message": message, "data": data}
    response_dict = {}
    for key, value in result_dict.items():
        if value is None and key != "code":
            continue
        else:
            response_dict[key] = value
    response = (response_dict)
    if auth:
        response.headers["Authorization"] = auth
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Method"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Expose-Headers"] = "Authorization"
    return response


def construct_result(code=settings.RetCode.DATA_ERROR, message='data is missing'):
    import re
    result_dict = {"code": code, "message": re.sub(r"rag", "seceum", message, flags=re.IGNORECASE)}
    response = {}
    for key, value in result_dict.items():
        if value is None and key != "code":
            continue
        else:
            response[key] = value
    return response


def construct_json_result(code=settings.RetCode.SUCCESS, message='success', data=None):
    if data is None:
        return {"code": code, "message": message}
    else:
        return {"code": code, "message": message, "data": data}


def construct_error_response(e):
    logging.exception(e)
    try:
        if e.code == 401:
            return construct_json_result(code=settings.RetCode.UNAUTHORIZED, message=repr(e))
    except BaseException:
        pass
    if len(e.args) > 1:
        return construct_json_result(code=settings.RetCode.EXCEPTION_ERROR, message=repr(e.args[0]), data=e.args[1])
    return construct_json_result(code=settings.RetCode.EXCEPTION_ERROR, message=repr(e))


def token_required(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        authorization_list=flask_request.headers.get('Authorization').split()
        if len(authorization_list) < 2:
            return get_json_result(data=False,message="Please check your authorization format.")
        token = authorization_list[1]
        objs = APIToken.query(token=token)
        if not objs:
            return get_json_result(
                data=False, message='Token is not valid!', code=settings.RetCode.AUTHENTICATION_ERROR
            )
        kwargs['tenant_id'] = objs[0].tenant_id
        return func(*args, **kwargs)

    return decorated_function


def get_result(code=settings.RetCode.SUCCESS, message="", data=None):
    if code == 0:
        if data is not None:
            response = {"code": code, "data": data}
        else:
            response = {"code": code}
    else:
        response = {"code": code, "message": message}
    return response


def get_error_data_result(message='Sorry! Data missing!', code=settings.RetCode.DATA_ERROR,
                          ):
    import re
    result_dict = {
        "code": code,
        "message": re.sub(
            r"rag",
            "seceum",
            message,
            flags=re.IGNORECASE)}
    response = {}
    for key, value in result_dict.items():
        if value is None and key != "code":
            continue
        else:
            response[key] = value
    return response


def generate_confirmation_token(tenent_id):
    serializer = URLSafeTimedSerializer(tenent_id)
    return "ragflow-" + serializer.dumps(get_uuid(), salt=tenent_id)[2:34]


def valid(permission,valid_permission,language,valid_language,chunk_method,valid_chunk_method):
    if valid_parameter(permission,valid_permission):
        return valid_parameter(permission,valid_permission)
    if valid_parameter(language,valid_language):
        return valid_parameter(language,valid_language)
    if valid_parameter(chunk_method,valid_chunk_method):
        return valid_parameter(chunk_method,valid_chunk_method)

def valid_parameter(parameter,valid_values):
    if parameter and parameter not in valid_values:
       return get_error_data_result(f"'{parameter}' is not in {valid_values}")

def get_parser_config(chunk_method,parser_config):
    if parser_config:
        return parser_config
    if not chunk_method:
        chunk_method = "naive"
    key_mapping={"naive":{"chunk_token_num": 128, "delimiter": "\\n!?;。；！？", "html4excel": False,"layout_recognize": True, "raptor": {"use_raptor": False}},
                 "qa":{"raptor":{"use_raptor":False}},
                 "resume":None,
                 "manual":{"raptor":{"use_raptor":False}},
                 "table":None,
                 "paper":{"raptor":{"use_raptor":False}},
                 "book":{"raptor":{"use_raptor":False}},
                 "laws":{"raptor":{"use_raptor":False}},
                 "presentation":{"raptor":{"use_raptor":False}},
                 "one":None,
                 "knowledge_graph":{"chunk_token_num":8192,"delimiter":"\\n!?;。；！？","entity_types":["organization","person","location","event","time"]},
                 "email":None,
                 "picture":None}
    parser_config=key_mapping[chunk_method]
    return parser_config