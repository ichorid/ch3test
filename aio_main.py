@app.get("/asgi")
async def root(request: ASGIRequest):
    return {
        "message": "Hello World",
        "root_path": request.scope.get("root_path")
    }


aiohttp_app = web.Application()

# Create ASGIResource which handle
# any request startswith "/asgi"
asgi_resource = ASGIResource(app)

# Register resource
aiohttp_app.router.register_resource(asgi_resource)

# [Optional]
asgi_resource.lifespan_mount(
    aiohttp_app,
    startup=True,
    # By default starlette didn't
    # handle "lifespan.shutdown"
    shutdown=False,
)

if __name__ == "__main__":
    # Start the application
    web.run_app(aiohttp_app)
