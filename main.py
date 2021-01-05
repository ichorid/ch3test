import hashlib
import os
import sys
from asyncio import ensure_future
from pprint import pprint
from typing import Optional

import uvicorn
from fastapi import Depends
from fastapi import FastAPI
from fastapi_etag import Etag
from starlette.requests import Request
from starlette.staticfiles import StaticFiles

from c3comm import C3Community
from ipv8.community import Community
from ipv8.configuration import ConfigBuilder, WalkerDefinition, Strategy
from ipv8_service import IPv8
from utils import hash_str_to_int

app = FastAPI()
app.mount("/static", StaticFiles(directory="wiki1/output"), name="static")



@app.get("/")
async def read_root():
    return {"Hello": "World"}


@app.get("/status")
async def get_status():
    return {"username": "foobaruser", "anonymous": "false"}


@app.get("/tiddlers.json")
async def get_tiddlers2(filter: Optional[str] = None):
    tiddlers_dict = app.state.c3comm.tsapa.resources
    tiddler_titles_list = [t["title"] for t in tiddlers_dict.values()]
    print (tiddler_titles_list)
    return {"modifications": tiddler_titles_list, "deletions": []}


@app.get("/tiddlers/{tiddler_title:path}")
async def get_tiddlers(tiddler_title: str):
    tiddlers_dict = app.state.c3comm.tsapa.resources
    title_hash = hash_str_to_int(tiddler_title)
    tiddler = tiddlers_dict.get(title_hash, {})
    return tiddler


async def put_tiddler_etag(request: Request):
    json_obj = await request.json()
    h = str(hashlib.sha256(str(json_obj).encode('utf8')))
    #pprint(json_obj)
    return "recipes/" + request.path_params["tiddler_title"] + "/" + "123" + ":" + h


@app.put("/tiddlers/{tiddler_title:path}", dependencies=[Depends(Etag(put_tiddler_etag))])
async def save_tiddler(request: Request, tiddler_title: str):
    tiddlers_dict = app.state.c3comm.tsapa.resources
    json_obj = await request.json()
    #pprint(json_obj)
    assert tiddler_title == json_obj["title"]
    if json_obj.get('text'):
        fields = json_obj.get('fields')
        if fields:
            if 'draft.of' in fields:
                return {}
        title_hash = hash_str_to_int(tiddler_title)
        #tiddlers_dict.[title_hash] = json_obj
        app.state.c3comm.tsapa.add_resource(title_hash, dict(json_obj))
        print ("SAVE TIDDLER")



    print("RESOURCES", app.state.c3comm.tsapa.resources)


    return {}


class MyCommunity(Community):
    community_id = os.urandom(20)


@app.on_event("startup")
async def startup_event():
    ipv8 = await ensure_future(start_communities())
    app.state.ipv8 = ipv8
    for comm in app.state.ipv8.overlays:
        if isinstance(comm, C3Community):
            app.state.c3comm = comm
            break
    print(app.state.ipv8.overlays)


# @app.put("/recipes/undefined/tiddlers")

async def start_communities():
    i = 0
    if len(sys.argv)>1:
        i = int(sys.argv[1])
    builder = ConfigBuilder().clear_keys().clear_overlays()
    builder.add_key("my peer", "medium", f"ec{i}.pem")
    builder.add_overlay("C3Comm", "my peer", [WalkerDefinition(Strategy.RandomWalk, 10, {'timeout': 3.0})], {},
                        [('started',)])
    # builder.add_overlay("MyCommunity", "my peer", [WalkerDefinition(Strategy.RandomWalk, 10, {'timeout': 3.0})], {}, [])
    ipv8 = IPv8(builder.finalize(), extra_communities={'C3Comm': C3Community})
    await ipv8.start()
    return ipv8


if __name__ == "__main__":

    port = 8000
    if len(sys.argv)>1:
        port = int(sys.argv[1])

    uvicorn.run(app, host="0.0.0.0", port=port)
