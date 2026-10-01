"""试卷真实导出引擎（Markdown 与 Word .docx 格式排版渲染）。

特性：
1. 100% 读取 PaperQuestion 快照字段（stem_snapshot, answer_snapshot, analysis_snapshot, options_snapshot），绝不回查实时题库；
2. Markdown 导出包含卷头、作答信息横线、大题分类、小题题干、选项、参考答案速查表及详细解析页；
3. Word (.docx) 导出支持标准 A4 页面排版、各级标题样式、小题分值标注、本地配图自动解析嵌入、分页符隔离试题区与《参考答案与解析》；
4. 导出直接输出字节流，支持直接通过 HTTP 文件附件下载（Content-Disposition）。
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import docx
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

from app.core.config import settings
from app.models.paper import Paper, PaperQuestion

_RE_MARKDOWN_IMAGE = re.compile(r"!\[(.*?)\]\((.*?)\)")


def export_markdown(paper: Paper, questions: list[PaperQuestion]) -> str:
    """导出试卷为标准 Markdown 文本格式。"""
    lines: list[str] = []

    # 1. 卷头信息
    lines.append(f"# {paper.title}")
    lines.append("")
    desc = f"> {paper.description}" if paper.description else ""
    if desc:
        lines.append(desc)
        lines.append("")
    lines.append(
        f"**满分**：{paper.total_score} 分 &nbsp;|&nbsp; **考试时间**：{paper.duration_minutes} 分钟"
    )
    lines.append("")
    lines.append("班级：__________________ &nbsp;&nbsp;&nbsp;&nbsp; 姓名：__________________ &nbsp;&nbsp;&nbsp;&nbsp; 考号：__________________")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 2. 试题部分（按大题 section 分组）
    sections_map: dict[str, list[PaperQuestion]] = {}
    for pq in questions:
        sec = pq.section or "试题部分"
        sections_map.setdefault(sec, []).append(pq)

    for sec_name, sec_questions in sections_map.items():
        sec_total_score = sum(q.score for q in sec_questions)
        lines.append(f"## {sec_name}（共 {len(sec_questions)} 题，共 {sec_total_score:.1f} 分）")
        lines.append("")

        for q in sec_questions:
            lines.append(f"**{q.display_order}.** ({q.score:.1f}分) {q.stem_snapshot}")
            lines.append("")
            if q.options_snapshot:
                for opt in q.options_snapshot:
                    lines.append(f"- {opt}")
                lines.append("")

    # 3. 答案与解析分割线
    lines.append("---")
    lines.append("")
    lines.append(f"# 《{paper.title}》参考答案与解析")
    lines.append("")

    # 4. 参考答案速查表
    lines.append("## 一、参考答案速查")
    lines.append("")
    lines.append("| 题号 | 大题归属 | 满分 | 参考答案 |")
    lines.append("|:---:|:---|:---:|:---|")
    for q in questions:
        ans_text = (q.answer_snapshot or "略").replace("\n", " ").replace("|", "\\|")
        lines.append(f"| {q.display_order} | {q.section or '-'} | {q.score:.1f} | {ans_text} |")
    lines.append("")

    # 5. 详细解析
    lines.append("## 二、试题详细解析")
    lines.append("")
    for q in questions:
        lines.append(f"### 第 {q.display_order} 题 ({q.score:.1f}分)")
        lines.append(f"**【参考答案】**：{q.answer_snapshot or '略'}")
        lines.append("")
        lines.append("**【解题思路与解析】**：")
        lines.append(f"{q.analysis_snapshot or '略'}")
        lines.append("")

    return "\n".join(lines)


def export_docx(
    paper: Paper,
    questions: list[PaperQuestion],
    media_root: str | Path | None = None,
) -> bytes:
    """导出试卷为高质量排版的 Word (.docx) 文档。"""
    doc = docx.Document()

    # 页面边距设为标准 2cm
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)

    # 1. 试卷主标题
    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_p.paragraph_format.space_after = Pt(6)
    title_p.paragraph_format.space_before = Pt(0)
    title_run = title_p.add_run(paper.title)
    title_run.font.size = Pt(18)
    title_run.font.bold = True

    # 2. 副标题与考生信息
    info_p = doc.add_paragraph()
    info_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    info_p.paragraph_format.space_after = Pt(14)
    info_run = info_p.add_run(
        f"满分：{paper.total_score:.1f}分   考试时长：{paper.duration_minutes}分钟   "
        "班级：___________   姓名：___________   考号：___________"
    )
    info_run.font.size = Pt(10.5)

    # 3. 试题部分
    sections_map: dict[str, list[PaperQuestion]] = {}
    for pq in questions:
        sec = pq.section or "试题部分"
        sections_map.setdefault(sec, []).append(pq)

    m_root = Path(media_root or settings.media_root)

    for sec_name, sec_questions in sections_map.items():
        sec_total_score = sum(q.score for q in sec_questions)
        sec_p = doc.add_paragraph()
        sec_p.paragraph_format.space_before = Pt(10)
        sec_p.paragraph_format.space_after = Pt(4)
        sec_run = sec_p.add_run(f"{sec_name}（共 {len(sec_questions)} 题，共 {sec_total_score:.1f} 分）")
        sec_run.font.size = Pt(13)
        sec_run.font.bold = True
        sec_run.font.color.rgb = RGBColor(0x1F, 0x29, 0x37)

        for q in sec_questions:
            # 题干段落
            qp = doc.add_paragraph()
            qp.paragraph_format.space_before = Pt(4)
            qp.paragraph_format.space_after = Pt(2)
            qp.paragraph_format.line_spacing = 1.25

            order_run = qp.add_run(f"{q.display_order}. ({q.score:.1f}分) ")
            order_run.font.bold = True
            order_run.font.size = Pt(11)

            # 过滤提取题干中的图片标签与正文
            stem_text = q.stem_snapshot
            image_urls = _RE_MARKDOWN_IMAGE.findall(stem_text)
            clean_stem = _RE_MARKDOWN_IMAGE.sub("", stem_text).strip()

            stem_run = qp.add_run(clean_stem)
            stem_run.font.size = Pt(11)

            # 插入选项
            if q.options_snapshot:
                for opt in q.options_snapshot:
                    opt_p = doc.add_paragraph()
                    opt_p.paragraph_format.left_indent = Inches(0.25)
                    opt_p.paragraph_format.space_before = Pt(1)
                    opt_p.paragraph_format.space_after = Pt(1)
                    opt_run = opt_p.add_run(opt)
                    opt_run.font.size = Pt(10.5)

            # 插入题干配图
            for alt, img_url in image_urls:
                img_path = _resolve_local_image_path(img_url, m_root)
                if img_path and img_path.is_file():
                    try:
                        pic_p = doc.add_paragraph()
                        pic_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        pic_p.paragraph_format.space_before = Pt(4)
                        pic_p.paragraph_format.space_after = Pt(4)
                        doc.add_picture(str(img_path), width=Inches(3.2))
                        if alt:
                            cap_p = doc.add_paragraph()
                            cap_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                            cap_run = cap_p.add_run(f"图：{alt}")
                            cap_run.font.size = Pt(9)
                            cap_run.font.italic = True
                    except Exception:
                        pass

    # 4. 插入分页符，隔离答案与解析
    doc.add_page_break()

    # 5. 参考答案与解析标题
    ans_title_p = doc.add_paragraph()
    ans_title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    ans_title_p.paragraph_format.space_before = Pt(8)
    ans_title_p.paragraph_format.space_after = Pt(12)
    ans_title_run = ans_title_p.add_run(f"《{paper.title}》参考答案与解析")
    ans_title_run.font.size = Pt(16)
    ans_title_run.font.bold = True

    # 6. 参考答案速查表
    table_sec_p = doc.add_paragraph()
    table_sec_run = table_sec_p.add_run("一、参考答案速查表")
    table_sec_run.font.size = Pt(12)
    table_sec_run.font.bold = True

    table = doc.add_table(rows=1, cols=4)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr_cells = table.rows[0].cells
    headers = ["题号", "所属大题", "分值", "参考答案"]
    for i, h in enumerate(headers):
        hdr_cells[i].text = h
        hdr_cells[i].vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        for p in hdr_cells[i].paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for r in p.runs:
                r.font.bold = True
                r.font.size = Pt(10)

    for q in questions:
        row_cells = table.add_row().cells
        row_cells[0].text = str(q.display_order)
        row_cells[1].text = q.section or "-"
        row_cells[2].text = f"{q.score:.1f}"
        row_cells[3].text = q.answer_snapshot or "略"
        for i in range(4):
            row_cells[i].vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            for p in row_cells[i].paragraphs:
                if i < 3:
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for r in p.runs:
                    r.font.size = Pt(9.5)

    doc.add_paragraph().paragraph_format.space_after = Pt(10)

    # 7. 详细解析列表
    detail_sec_p = doc.add_paragraph()
    detail_sec_run = detail_sec_p.add_run("二、试题详细解析与步骤")
    detail_sec_run.font.size = Pt(12)
    detail_sec_run.font.bold = True

    for q in questions:
        qp = doc.add_paragraph()
        qp.paragraph_format.space_before = Pt(6)
        qp.paragraph_format.space_after = Pt(2)
        q_run = qp.add_run(f"第 {q.display_order} 题 ({q.score:.1f}分)")
        q_run.font.bold = True
        q_run.font.size = Pt(10.5)

        ap = doc.add_paragraph()
        ap.paragraph_format.left_indent = Inches(0.2)
        ap.paragraph_format.space_before = Pt(1)
        ap.paragraph_format.space_after = Pt(1)
        a_lbl = ap.add_run("【参考答案】 ")
        a_lbl.font.bold = True
        a_lbl.font.size = Pt(10)
        a_val = ap.add_run(q.answer_snapshot or "略")
        a_val.font.size = Pt(10)

        exp_p = doc.add_paragraph()
        exp_p.paragraph_format.left_indent = Inches(0.2)
        exp_p.paragraph_format.space_before = Pt(1)
        exp_p.paragraph_format.space_after = Pt(4)
        exp_lbl = exp_p.add_run("【解题思路】 ")
        exp_lbl.font.bold = True
        exp_lbl.font.size = Pt(10)
        exp_val = exp_p.add_run(q.analysis_snapshot or "略")
        exp_val.font.size = Pt(10)

    # 保存文档到内存流
    file_stream = io.BytesIO()
    doc.save(file_stream)
    return file_stream.getvalue()


def _resolve_local_image_path(img_url: str, media_root: Path) -> Path | None:
    """尝试将图片 URL 或路径解析为本地物理文件。"""
    if not img_url:
        return None
    # 提取 /static/ 后面的相对路径
    clean_url = img_url.split("?")[0]
    if "/static/" in clean_url:
        rel_path = clean_url.split("/static/", 1)[1]
        p = media_root / rel_path
        if p.exists():
            return p
    # 直接在 media_root 下匹配
    filename = Path(clean_url).name
    matches = list(media_root.rglob(filename))
    if matches:
        return matches[0]
    return None
