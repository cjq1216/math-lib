"""
LLM 服务 - 切题 / 打标 / Embedding

prompt 模板集中管理，方便调优。
"""
import json
import re

from app.core.config import settings
from app.services.llm_client import get_llm_client

# ====== 切题 prompt ======
SPLIT_PROMPT = """你是初中数学题目切分专家。

输入是一份试卷的纯文本（可能含 LaTeX 公式 $...$），需要切分成独立题目。

要求：
1. 准确识别每道题的题号
2. 分离题干、选项（小问）、答案、解析
3. 保留 LaTeX 公式原样
4. 几何题保留 [图:description] 占位
5. 难度评估参考：1=简单（直接套公式）/ 2=中等（1-2步推理）/ 3=较难（多步综合）/ 4=困难（压轴题）/ 5=竞赛

输出严格 JSON：
{
  "questions": [
    {
      "number": "1",
      "stem": "题干文字...",
      "options": ["A. ...", "B. ..."],
      "sub_questions": [{"label": "(1)", "stem": "..."}],
      "answer": "...",
      "analysis": "...",
      "knowledge_points": ["一元二次方程", "求根公式"],
      "difficulty": 3,
      "question_type": "choice_single",
      "confidence": 0.92
    }
  ]
}

只输出 JSON，不要其他解释。
"""


# ====== 打标 prompt ======
TAG_PROMPT = """你是初中数学题目分析与打标专家。

输入是一道题目的题干（可能含 LaTeX 公式）。

任务：
1. 判断题型（choice_single 单选 / choice_multi 多选 / fill 填空 / judge 判断 / solution 解答 / proof 证明）
2. 评估难度（1-5）
3. 提取涉及的核心知识点（2-5 个，使用通用名称，如"一元二次方程"、"勾股定理"）

输出严格 JSON：
{
  "question_type": "choice_single",
  "difficulty": 3,
  "knowledge_points": ["一元二次方程", "求根公式"],
  "confidence": 0.92
}

只输出 JSON。
"""


# ====== 核心函数 ======

async def split_exam_questions(text: str) -> dict:
    """
    切分试卷文本为结构化题目

    Args:
        text: 试卷纯文本（LaTeX 公式用 $...$）

    Returns:
        {"questions": [...]}
    """
    client = get_llm_client()

    # 防止超 token：分段调用
    # 简单实现：每 5000 字一段
    chunks = _chunk_text(text, max_chars=5000)
    all_questions = []

    for chunk in chunks:
        try:
            content = await client.chat(
                messages=[
                    {"role": "system", "content": SPLIT_PROMPT},
                    {"role": "user", "content": f"请切分以下试卷：\n\n{chunk}"},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            result = json.loads(content)
            all_questions.extend(result.get("questions", []))
        except Exception as e:
            # 单段失败不影响整体
            print(f"切题失败: {e}")

    return {"questions": all_questions, "total": len(all_questions)}


async def auto_tag_question(
    stem: str,
    options: list[str] | None = None,
    answer: str | None = None,
) -> dict:
    """单个题目自动打标"""
    client = get_llm_client()

    user_msg = f"题目：{stem}"
    if options:
        user_msg += "\n选项：\n" + "\n".join(options)
    if answer:
        user_msg += f"\n答案：{answer}"

    try:
        content = await client.chat(
            messages=[
                {"role": "system", "content": TAG_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        return json.loads(content)
    except Exception as e:
        return {"error": str(e)}


async def embed_text(text: str) -> list[float]:
    """
    生成 embedding 向量

    用于：
    - 题目入库时去重检测
    - 相似题推荐
    - 错题本推荐
    """
    # 清洗：去掉 LaTeX 符号保留语义
    clean = _strip_latex(text)

    headers = {
        "Authorization": f"Bearer {settings.embedding_api_key or settings.minimax_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.embedding_model,
        "input": clean,
    }
    async with __import__("httpx").AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{settings.embedding_base_url}/embeddings",
            headers=headers,
            json=payload,
        )
        r.raise_for_status()
        data = r.json()
        return data["data"][0]["embedding"]


# ====== 辅助 ======

def _chunk_text(text: str, max_chars: int = 5000) -> list[str]:
    """文本分段，按段落切"""
    paragraphs = text.split("\n\n")
    chunks = []
    current = ""
    for p in paragraphs:
        if len(current) + len(p) > max_chars and current:
            chunks.append(current)
            current = p
        else:
            current += "\n\n" + p
    if current:
        chunks.append(current)
    return chunks


def _strip_latex(text: str) -> str:
    """去掉 LaTeX 标签，保留可读文本"""
    # $...$ → 保留内容
    text = re.sub(r"\$([^$]+)\$", r"\1", text)
    # \\frac{a}{b} → a/b
    text = re.sub(r"\\frac\{([^}]+)\}\{([^}]+)\}", r"\1/\2", text)
    # \\sqrt{a} → sqrt(a)
    text = re.sub(r"\\sqrt\{([^}]+)\}", r"sqrt(\1)", text)
    # \\times → *
    text = text.replace("\\times", "*").replace("\\cdot", "*")
    # 下标
    text = re.sub(r"_\{([^}]+)\}", r"_\1", text)
    text = re.sub(r"\^\{([^}]+)\}", r"^\1", text)
    return text.strip()
