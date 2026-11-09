import os
import uvicorn
from .app import create_app

if __name__=='__main__':
    os.umask(0o077)
    uvicorn.run(create_app(),host='127.0.0.1',port=int(os.environ.get('DAY14_PORT','8141')),workers=1,proxy_headers=False,access_log=False,log_level='warning')
