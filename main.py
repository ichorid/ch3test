from pprint import pprint
from typing import Optional

import uvicorn
from fastapi import FastAPI, Depends
from starlette.requests import Request
from starlette.staticfiles import StaticFiles

from aiohttp import web
from fastapi import FastAPI
from starlette.requests import Request as ASGIRequest

from aiohttp_asgi import ASGIResource

from fastapi_etag import Etag, add_exception_handler

app = FastAPI()
app.mount("/static", StaticFiles(directory="wiki1/output"), name="static")


tiddlers_dict = {}

@app.get("/")
async def read_root():
    return {"Hello": "World"}

@app.get("/status")
async def get_status():
    return {"username": "foobaruser", "anonymous": "false"}

@app.get("/tiddlers.json")
async def get_tiddlers(filter: Optional[str] = None):
    return {"modifications": list(tiddlers_dict), "deletions": []}

@app.get("/tiddlers/{tiddler_title:path}")
async def get_tiddlers(tiddler_title:str):
    tiddler = tiddlers_dict.get(tiddler_title, {})
    return tiddler

async def put_tiddler_etag(request: Request):
    json_obj = await request.json()
    h = str(hash(str(json_obj)))
    print("ETAG")
    pprint (json_obj)
    return "recipes/" + request.path_params["tiddler_title"] + "/" + "123" + ":" + h

@app.put("/tiddlers/{tiddler_title:path}", dependencies=[Depends(Etag(put_tiddler_etag))])
async def save_tiddler(request:Request, tiddler_title:str):
    json_obj = await request.json()
    pprint (json_obj)
    assert tiddler_title == json_obj["title"]
    if json_obj.get('text'):
        fields = json_obj.get('fields')
        if fields:
            if 'draft.of' in fields:
                return {}
        tiddlers_dict[tiddler_title] = json_obj

    return {}

#@app.put("/recipes/undefined/tiddlers")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
