from fastapi import FastAPI

from codecraft_api.app import create_app

# Settings are read when the factory runs, at import time, so a missing or blank
# required value stops the process before the application starts serving requests.
app: FastAPI = create_app()
