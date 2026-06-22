"""RAG API 路由 - 文档管理、问答、群组配置。"""

import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, Form
from pydantic import BaseModel
from typing import Optional

from server.db import db

logger = logging.getLogger("mobilerun.server")

router = APIRouter(prefix="/api/rag", tags=["rag"])

# 文档上传目录
RAG_UPLOAD_DIR = Path(__file__).parent.parent.parent / "data" / "rag_documents"
RAG_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ── 数据模型 ──

class ChatRequest(BaseModel):
    """问答请求。"""
    question: str
    session_id: str
    source: str = "web"
    language: Optional[str] = None
    include_translation: bool = True


class GroupCreate(BaseModel):
    """群组配置创建请求。"""
    chat_name: str
    source: str
    device_id: Optional[str] = None
    default_language: str = "pt"
    rag_enabled: bool = True


class GroupUpdate(BaseModel):
    """群组配置更新请求。"""
    default_language: Optional[str] = None
    rag_enabled: Optional[bool] = None


# ── 文档管理 API ──

@router.get("/documents")
async def get_documents(status: str = "active"):
    """获取文档列表。"""
    documents = db.load_rag_documents(status=status)
    return {"documents": documents, "total": len(documents)}


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    language: str = Form("auto")
):
    """上传文档并解析。"""
    # 验证文件类型
    filename = file.filename
    suffix = Path(filename).suffix.lower()
    if suffix not in [".docx", ".doc", ".pdf", ".txt"]:
        raise HTTPException(status_code=400, detail="只支持 .docx、.pdf 和 .txt 文件")

    # 验证文件大小（10MB）
    MAX_SIZE = 10 * 1024 * 1024
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="文件大小不能超过 10MB")

    # 保存文件
    file_id = str(uuid.uuid4())[:8]
    save_filename = f"{file_id}_{filename}"
    file_path = RAG_UPLOAD_DIR / save_filename
    with open(file_path, "wb") as f:
        f.write(content)

    # 解析文档
    from server.rag.document_parser import parse_document
    from server.rag.language_detector import detect_language
    from server.rag.text_splitter import semantic_split
    from server.rag.vectorstore import RagVectorStore

    try:
        # 解析
        text = parse_document(str(file_path), suffix.lstrip("."))

        # 语言检测
        if language == "auto":
            language = detect_language(text)

        # 切片（增大 overlap 以保持上下文完整性）
        chunks = semantic_split(text, chunk_size=400, overlap=150)

        # 保存到数据库
        doc_id = db.append_rag_document({
            "filename": filename,
            "file_path": str(file_path),
            "parsed_text": text,
            "chunk_count": len(chunks),
            "language": language,
            "uploaded_at": datetime.now().isoformat(),
            "status": "active"
        })

        # 存入向量库
        metadata_list = [
            {
                "doc_id": doc_id,
                "filename": filename,
                "language": language,
                "chunk_index": i
            }
            for i in range(len(chunks))
        ]
        await RagVectorStore.add_documents(doc_id, chunks, metadata_list)

        return {
            "id": doc_id,
            "filename": filename,
            "language": language,
            "chunk_count": len(chunks),
            "message": "文档上传成功"
        }

    except Exception as e:
        logger.error(f"文档处理失败：{e}")
        # 清理文件
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"文档处理失败：{str(e)}")


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: int):
    """删除文档。"""
    # 获取文档
    doc = db.get_rag_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    # 从向量库删除
    from server.rag.vectorstore import RagVectorStore
    await RagVectorStore.delete_documents(doc_id)

    # 标记为 archived
    db.delete_rag_document(doc_id)

    return {"message": "文档已删除"}


# ── 问答 API ─

@router.post("/chat")
async def chat(request: ChatRequest):
    """RAG 问答。"""
    from server.rag.chat_engine import RagChatEngine

    result = await RagChatEngine.chat(
        question=request.question,
        session_id=request.session_id,
        source=request.source,
        language=request.language,
        include_translation=request.include_translation
    )

    # 保存问答历史
    db.append_rag_chat_history({
        "session_id": request.session_id,
        "source": request.source,
        "question": request.question,
        "answer": result["answer"],
        "language": result.get("language"),
        "source_docs": result.get("source_docs", []),
        "created_at": datetime.now().isoformat()
    })

    return {
        "answer": result["answer"],
        "language": result.get("language"),
        "source_docs": result.get("source_docs", []),
        "translation": result.get("translation", "")
    }


@router.get("/history")
async def get_history(
    session_id: str = None,
    source: str = None,
    limit: int = 50
):
    """获取问答历史。"""
    history = db.get_rag_chat_history(session_id=session_id, source=source, limit=limit)
    return {"history": history, "total": len(history)}


# ── 群组配置 API ──

@router.get("/groups")
async def get_groups(source: str = None):
    """获取群组配置列表。"""
    groups = db.load_chat_groups(source=source)
    return {"groups": groups, "total": len(groups)}


@router.post("/groups")
async def add_group(group: GroupCreate):
    """添加群组配置。"""
    group_id = db.append_chat_group({
        "chat_name": group.chat_name,
        "source": group.source,
        "device_id": group.device_id,
        "default_language": group.default_language,
        "rag_enabled": group.rag_enabled,
        "created_at": datetime.now().isoformat()
    })

    if group_id == 0:
        raise HTTPException(status_code=409, detail="群组配置已存在")

    return {"id": group_id, "message": "群组配置已添加"}


@router.put("/groups/{chat_name}")
async def update_group(chat_name: str, group: GroupUpdate, source: str = None):
    """更新群组配置。"""
    if not source:
        raise HTTPException(status_code=400, detail="source 参数必填")

    updates = {}
    if group.default_language is not None:
        updates["default_language"] = group.default_language
    if group.rag_enabled is not None:
        updates["rag_enabled"] = 1 if group.rag_enabled else 0

    db.update_chat_group(chat_name, source, updates)

    return {"message": "群组配置已更新"}


@router.delete("/groups/{chat_name}")
async def delete_group(chat_name: str, source: str = None):
    """删除群组配置。"""
    if not source:
        raise HTTPException(status_code=400, detail="source 参数必填")

    db.delete_chat_group(chat_name, source)

    return {"message": "群组配置已删除"}
