#!/bin/bash
# init.sh

# 等待数据库就绪（如果需要）
# while ! nc -z $DB_HOST $DB_PORT; do
#   sleep 1
# done

# 执行初始化操作
python -c "
from bisheng.database.init_data import init_default_data
from bisheng.services.utils import initialize_services
from bisheng.interface.utils import setup_llm_caching

initialize_services()
setup_llm_caching()
init_default_data()
"

touch /tmp/init_done