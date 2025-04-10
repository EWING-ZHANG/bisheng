# run_update_progress.py
from concurrent.futures import ThreadPoolExecutor
from bisheng.api.services.document_service import DocumentService
import time
import logging
import signal
import sys

def update_progress():
    while True:
        try:
            time.sleep(3)
            DocumentService.update_progress()
            logging.info("update progress")
        except Exception as e:
            logging.exception("update_progress exception")

def main():
    # 注册信号处理，确保优雅退出
    def signal_handler(sig, frame):
        logging.info("Shutting down...")
        executor.shutdown(wait=False)
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # 启动线程池
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(update_progress)
        # 阻塞主线程，防止进程退出
        while True:
            time.sleep(3600)  # 长时间睡眠避免高频空转

if __name__ == '__main__':
    main()
