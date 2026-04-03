from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.database import Base, engine
from app.routers import agents, auth, tasks, ui

settings = get_settings()
app = FastAPI(title='KYSSCHECK', docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.middleware('http')
async def security_middleware(request: Request, call_next):
    if request.url.scheme != 'https' and settings.enforce_https:
        if request.headers.get('x-forwarded-proto') != 'https':
            return JSONResponse(status_code=400, content={'detail': 'Требуется HTTPS'})
    body = await request.body()
    if len(body) > 50_000:
        return JSONResponse(status_code=413, content={'detail': 'Слишком большой payload'})

    async def receive_again():
        return {'type': 'http.request', 'body': body, 'more_body': False}

    request = Request(request.scope, receive=receive_again)
    response = await call_next(request)
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@app.get('/healthz')
def healthz():
    return {'status': 'ok'}


app.include_router(auth.router)
app.include_router(agents.router)
app.include_router(tasks.router)
app.include_router(ui.router)


Base.metadata.create_all(bind=engine)
