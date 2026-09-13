"""
后台任务管理服务

替代同步 LLM 调用：
- 教师点"切题" → 创建 task → 立即返回 task_id
- 后台协程跑 LLM → 更新 task 状态
- 前端轮询查 task 状态

MVP 用 FastAPI BackgroundTasks 实现；后期切 Celery 改 base.py 即可。
"""

import traceback
from datetime import datetime
from typing import Any, Callable

from sqlmodel import Session

from app.models.background_task import BackgroundTask, TaskStatus, TaskType


def create_task(
    session: Session,
    task_type: TaskType,
    payload: dict[str, Any] | None = None,
    resource_type: str | None = None,
    resource_id: int | None = None,
    created_by: int | None = None,
) -> BackgroundTask:
    """创建任务记录（status=pending）"""
    task = BackgroundTask(
        task_type=task_type,
        status=TaskStatus.PENDING,
        payload=payload,
        resource_type=resource_type,
        resource_id=resource_id,
        created_by=created_by,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def start_task(session: Session, task_id: int) -> None:
    """标记任务开始执行"""
    task = session.get(BackgroundTask, task_id)
    if not task:
        return
    task.status = TaskStatus.RUNNING
    task.started_at = datetime.utcnow()
    session.add(task)
    session.commit()


def update_progress(
    session: Session,
    task_id: int,
    progress: int,
    message: str | None = None,
) -> None:
    """更新任务进度（0-100）"""
    task = session.get(BackgroundTask, task_id)
    if not task:
        return
    task.progress = min(100, max(0, progress))
    if message:
        task.progress_message = message[:500]  # 截断防超长
    session.add(task)
    session.commit()


def finish_task(
    session: Session,
    task_id: int,
    result: dict[str, Any] | None = None,
) -> None:
    """标记任务成功完成"""
    task = session.get(BackgroundTask, task_id)
    if not task:
        return
    task.status = TaskStatus.SUCCESS
    task.progress = 100
    task.result = result or {}
    task.finished_at = datetime.utcnow()
    session.add(task)
    session.commit()


def fail_task(
    session: Session,
    task_id: int,
    error: Exception,
) -> None:
    """标记任务失败"""
    task = session.get(BackgroundTask, task_id)
    if not task:
        return
    task.status = TaskStatus.FAILED
    task.error_message = str(error)[:2000]
    task.error_traceback = traceback.format_exc()[:5000]
    task.finished_at = datetime.utcnow()
    session.add(task)
    session.commit()


async def run_async_task(
    task_id: int,
    func: Callable,
    *args,
    **kwargs,
) -> None:
    """
    异步执行任务的封装

    用法：
        await run_async_task(
            task_id=task.id,
            func=do_split_exam,
            source_id=source.id,
        )
    """
    from app.core.database import SessionLocal

    # 1. 标记开始
    with SessionLocal() as session:
        start_task(session, task_id)

    # 2. 执行（可能耗时 30-60 秒）
    try:
        result = await func(*args, **kwargs)

        # 3. 标记完成
        with SessionLocal() as session:
            finish_task(session, task_id, result=result if isinstance(result, dict) else None)
    except Exception as e:
        # 4. 标记失败
        with SessionLocal() as session:
            fail_task(session, task_id, e)
        # 不抛异常（后台任务不应影响主流程）
        print(f"Task {task_id} failed: {e}")


def schedule_task(
    background_tasks,
    session: Session,
    task_type: TaskType,
    func: Callable,
    payload: dict[str, Any] | None = None,
    resource_type: str | None = None,
    resource_id: int | None = None,
    created_by: int | None = None,
    **func_kwargs,
) -> BackgroundTask:
    """
    在 FastAPI 路由中调度一个后台任务

    用法：
        @router.post("/split")
        async def split_endpoint(payload: dict, bg: BackgroundTasks, session: Session = Depends(...)):
            task = schedule_task(
                background_tasks=bg,
                session=session,
                task_type=TaskType.SPLIT_EXAM,
                func=do_split_exam,
                payload=payload,
                resource_id=source_id,
                text=payload["text"],
            )
            return {"task_id": task.id}
    """
    # 创建任务记录
    task = create_task(
        session=session,
        task_type=task_type,
        payload=payload,
        resource_type=resource_type,
        resource_id=resource_id,
        created_by=created_by,
    )

    # 调度后台执行
    background_tasks.add_task(
        run_async_task,
        task_id=task.id,
        func=func,
        **func_kwargs,
    )

    return task
