"""LLM 服务 - 试卷切题 / 题目标注 / 线上 Embedding（带平滑降级与重试）。

特性：
1. 试卷长文本分段切题，支持实时进度汇报与部分成功（partial_success）；
2. 题目自动打标（智能识别题型、难度 1-5、知识点标签）；
3. 线上 Embedding 自动降级：当未配置 API Key 或接口调用异常时，记录警告日志并平滑跳过，绝不阻断业务接口。
"""

from __future__ import annotations

import re
from typing import Any, Callable

from loguru import logger

from app.core.config import settings
from app.services.llm_client import extract_json_payload, get_llm_client

SPLIT_PROMPT = """你是初中数学教研专家。请分析输入的数学试卷文本（包含 LaTeX 格式公式），将其结构化切分成独立的题目列表。

要求：
1. 准确识别每道题的题号（number）；
2. 识别题型（question_type: choice_single, choice_multi, fill, judge, solution, proof）；
3. 分离题干（stem）、选择题选项（options，如 ["A. ...", "B. ..."]）、解答题小问（sub_questions）、主答案（answer）及解析（analysis）；
4. 保留所有 LaTeX 公式原样（如 $x^2 + 1 = 0$）；
5. 预估题目难度（difficulty: 1 到 5 的整数，1最易，5最难）；
6. 预估考察的主要数学知识点名称（knowledge_points 字符串列表）。

请务必输出严格的 JSON 格式，顶层包含 "questions" 数组：
{
  "questions": [
    {
      "number": "1",
      "question_type": "choice_single",
      "difficulty": 2,
      "stem": "已知关于 $x$ 的一元二次方程...",
      "options": ["A. $x=1$", "B. $x=2$", "C. $x=3$", "D. $x=4$"],
      "answer": "A",
      "analysis": "根据求根公式计算得...",
      "knowledge_points": ["一元二次方程", "求根公式"],
      "sub_questions": []
    }
  ]
}

只输出纯 JSON，不要包含任何首尾额外的客套解释。
"""

TAG_PROMPT = """你是初中数学题目分析与标注专家。请对以下数学题目进行专业打标：
1. question_type：单选 choice_single / 多选 choice_multi / 填空 fill / 判断 judge / 解答 solution / 证明 proof；
2. difficulty：1-5 的整数；
3. knowledge_points：1-3 个核心初中数学知识点名称（列表）；
4. tags：考点特性标签（如 ["代数", "易错题"]）。

输出严格 JSON 格式：
{
  "question_type": "choice_single",
  "difficulty": 3,
  "knowledge_points": ["勾股定理"],
  "tags": ["几何", "期中"]
}
只输出 JSON。
"""


async def split_exam_questions(
    text: str,
    on_progress: Callable[[int, str], None] | None = None,
) -> dict[str, Any]:
    """对长文本试卷进行切题，分块调用线上大模型并归集所有题目。"""
    chunks = _chunk_text(text, max_chars=4000)
    total_chunks = len(chunks)
    all_questions: list[dict[str, Any]] = []
    failed_chunks: list[dict[str, Any]] = []

    client = get_llm_client()

    for idx, chunk in enumerate(chunks, start=1):
        if on_progress:
            progress_pct = int(10 + (idx / total_chunks) * 80)
            on_progress(progress_pct, f"正在分析试卷第 {idx}/{total_chunks} 分段...")

        messages = [
            {"role": "system", "content": SPLIT_PROMPT},
            {"role": "user", "content": f"试卷第 {idx} 部分文本内容如下：\n\n{chunk}"},
        ]

        try:
            raw_output = await client.chat(messages, temperature=0.1, max_tokens=4000)
            parsed = extract_json_payload(raw_output)

            qs = []
            if isinstance(parsed, dict) and "questions" in parsed:
                qs = parsed["questions"]
            elif isinstance(parsed, list):
                qs = parsed

            for item in qs:
                if isinstance(item, dict) and item.get("stem"):
                    normalized = _normalize_split_question(item, len(all_questions) + 1)
                    all_questions.append(normalized)

        except Exception as e:
            logger.warning(f"分段 {idx}/{total_chunks} 切题调用失败: {e}")
            failed_chunks.append({"chunk_index": idx, "error": str(e)})

    if on_progress:
        on_progress(100, f"切题完成，共成功识别 {len(all_questions)} 道题目")

    is_partial = len(failed_chunks) > 0 and len(all_questions) > 0
    return {
        "questions": all_questions,
        "total": len(all_questions),
        "partial": is_partial,
        "failed_chunks": failed_chunks,
    }


async def auto_tag_question(
    stem: str,
    options: list[str] | None = None,
    answer: str | None = None,
    question_id: int | None = None,
) -> dict[str, Any]:
    """单道题目自动智能打标。"""
    client = get_llm_client()

    user_content = f"题干：\n{stem}\n"
    if options:
        user_content += f"选项：\n{chr(10).join(options)}\n"
    if answer:
        user_content += f"答案：\n{answer}\n"

    messages = [
        {"role": "system", "content": TAG_PROMPT},
        {"role": "user", "content": user_content},
    ]

    try:
        raw_output = await client.chat(messages, temperature=0.1, max_tokens=1000)
        parsed = extract_json_payload(raw_output)
        if isinstance(parsed, dict):
            # 校验并限制难度 1-5
            diff = parsed.get("difficulty", 3)
            try:
                diff = max(1, min(5, int(diff)))
            except (ValueError, TypeError):
                diff = 3
            parsed["difficulty"] = diff
            return parsed
        return {"error": "解析打标结果格式异常"}
    except Exception as e:
        logger.warning(f"智能打标调用失败: {e}")
        return {"error": str(e)}


async def embed_text(text: str) -> list[float] | None:
    """计算文本的 Embedding 向量，支持无 Key / 接口故障时自动平滑降级（返回 None，不阻断主流程）。"""
    if not settings.minimax_api_key:
        logger.debug("未配置 MINIMAX_API_KEY，平滑跳过向量计算")
        return None

    clean_content = _strip_latex(text)
    if not clean_content:
        return None

    client = get_llm_client()
    try:
        vectors = await client.embed([clean_content[:1500]])
        if vectors and len(vectors) > 0:
            return vectors[0]
        return None
    except Exception as e:
        logger.warning(f"Embedding 向量生成失败 ({e})，已自动平滑降级跳过")
        return None


def _chunk_text(text: str, max_chars: int = 4000) -> list[str]:
    """按段落分割试卷长文本，避免跨题切断。"""
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_len = 0

    for p in paragraphs:
        p_len = len(p)
        if current_len + p_len > max_chars and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [p]
            current_len = p_len
        else:
            current_chunk.append(p)
            current_len += p_len

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks or [text]


def _strip_latex(text: str) -> str:
    """剥离 LaTeX 标志符号，提取适合语义向量检索的纯文字与公式简写。"""
    s = re.sub(r"\$+", "", text)
    s = re.sub(r"\\[a-zA-Z]+", " ", s)
    s = re.sub(r"[{}]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _normalize_split_question(raw: dict[str, Any], fallback_num: int) -> dict[str, Any]:
    """标准化大模型切出来的题目字典结构。"""
    qtype = raw.get("question_type") or "choice_single"
    valid_types = {"choice_single", "choice_multi", "fill", "judge", "solution", "proof"}
    if qtype not in valid_types:
        qtype = "choice_single" if raw.get("options") else "solution"

    diff = raw.get("difficulty") or 3
    try:
        diff = max(1, min(5, int(diff)))
    except (ValueError, TypeError):
        diff = 3

    options = raw.get("options")
    if options is not None and not isinstance(options, list):
        options = None

    subs = raw.get("sub_questions")
    if not isinstance(subs, list):
        subs = []

    kps = raw.get("knowledge_points")
    if not isinstance(kps, list):
        kps = []

    return {
        "number": str(raw.get("number") or fallback_num),
        "stem": str(raw.get("stem") or "").strip(),
        "question_type": qtype,
        "difficulty": diff,
        "options": options,
        "answer": str(raw.get("answer") or "").strip() or None,
        "analysis": str(raw.get("analysis") or "").strip() or None,
        "sub_questions": subs,
        "knowledge_points": [str(k).strip() for k in kps if str(k).strip()],
        "total_score": 3.0 if qtype == "choice_single" else (4.0 if qtype == "fill" else 10.0),
    }
