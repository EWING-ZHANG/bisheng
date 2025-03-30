# nohup uvicorn bisheng.main:app --host 0.0.0.0 --port 7860 --no-access-log --workers 2 &

# # -c 是指定celery的并发数
# celery -A bisheng.worker.main worker -l info -c 4


#
#
# 修改容器启动命令 启动ragflow启动需要执行的命令
#!/bin/bash

# 启动 debugpy 调试服务（如需生产环境可注释掉）
# python -m debugpy --listen 0.0.0.0:5678 --wait-for-client -m uvicorn bisheng.main:app --host 0.0.0.0 --port 7860 --no-access-log --workers 2 &

# 启动 Celery worker
celery -A bisheng.worker.main worker -l info -c 4 &

# 启动后台任务
python -c "
from concurrent.futures import ThreadPoolExecutor;
from bisheng.api.services.document_service import DocumentService;
import time, logging;

def update_progress():
    while True:
        time.sleep(3)
        try: DocumentService.update_progress()
        except: logging.exception('update_progress exception')

ThreadPoolExecutor(max_workers=1).submit(update_progress)
"

# 保持容器运行
wait
