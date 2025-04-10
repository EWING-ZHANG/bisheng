# update_progress.py
import time
import logging
from bisheng.api.services.document_service import DocumentService

logging.basicConfig(level=logging.INFO)

while True:
    try:
        DocumentService.update_progress()
        time.sleep(3)
    except Exception as e:
        logging.exception("Error in update_progress")