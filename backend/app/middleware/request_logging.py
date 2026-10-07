"""HTTP 请求日志与追踪中间件。

功能：
1. 提取或生成唯一 X-Request-ID 请求追踪标识，回填到响应头；
2. 精确记录请求耗时 (毫秒)；
3. 提取认证上下文 (用户名或匿名)，记录结构化访问日志；
4. 严格禁止打印 Authorization、Token、Cookie 及密码等敏感隐私数据。
"""

import time
import uuid
from typing import Callable

from fastapi import Request, Response
from jose import jwt
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求耗时统计与 Request-ID 追踪中间件"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 1. 提取或生成请求追踪 ID
        incoming_id = request.headers.get("X-Request-ID")
        if incoming_id and len(incoming_id) <= 64 and incoming_id.replace("-", "").isalnum():
            request_id = incoming_id
        else:
            request_id = uuid.uuid4().hex

        request.state.request_id = request_id

        # 2. 识别用户上下文 (不查库，直接解算已签名 JWT payload)
        actor = "anonymous"
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            try:
                payload = jwt.decode(
                    token,
                    settings.jwt_secret_key,
                    algorithms=[settings.jwt_algorithm],
                )
                actor = payload.get("sub", "authenticated_user")
            except Exception:
                actor = "invalid_token"

        start_time = time.perf_counter()

        try:
            response: Response = await call_next(request)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time-Ms"] = str(duration_ms)

            # 静态资源请求不刷屏，仅记录 API 与系统端点
            if not request.url.path.startswith("/static"):
                logger.info(
                    f"[{request_id}] {request.method} {request.url.path} -> {response.status_code} "
                    f"({duration_ms}ms) [actor={actor}]"
                )

            return response
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(
                f"[{request_id}] {request.method} {request.url.path} -> 500 ERROR "
                f"({duration_ms}ms) [actor={actor}]: {exc}"
            )
            raise
