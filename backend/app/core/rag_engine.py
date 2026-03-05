"""
RAG 知识引擎 — 结构感知切片（Structure-Aware Chunking）

切片策略：
  1. 按 Markdown 标题层级（#/##/###/####）识别章节边界
  2. 每个"章节"作为基础语义单元
  3. 若章节超过 max_chars 则在段落级别做二次分割
  4. 若章节过短（< min_chars）则与相邻章节合并
  5. 在每个 chunk 头部附加最近标题的面包屑路径，增强上下文
"""
from __future__ import annotations

import re
import time
import uuid
from pathlib import Path
from typing import Any

from app.config import settings
from app.models.schemas import ChunkMetadata, SeverityLevel, SOPChunk


# ─────────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────────

# 危险等级关键词 → severity 映射
_SEVERITY_KEYWORDS: dict[SeverityLevel, list[str]] = {
    SeverityLevel.CRITICAL: ["P0", "禁止", "立即", "紧急", "危化品", "爆炸", "着火", "致命"],
    SeverityLevel.HIGH:     ["P1", "告警", "高风险", "危险", "盐雾", "漏油", "泄漏", "切断"],
    SeverityLevel.MEDIUM:   ["P2", "注意", "检查", "超标", "偏差", "故障"],
    SeverityLevel.LOW:      ["P3", "建议", "参考", "记录"],
}

_ZONE_PATTERN = re.compile(r"ZONE-[A-Z\d]+|HZ-[A-Z\d]+|CK-[A-Z\d]+|BLDG-[A-Z\d]+")

_HEADER_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)


def _infer_severity(text: str) -> SeverityLevel:
    for level in (SeverityLevel.CRITICAL, SeverityLevel.HIGH, SeverityLevel.MEDIUM):
        if any(kw in text for kw in _SEVERITY_KEYWORDS[level]):
            return level
    return SeverityLevel.LOW


def _extract_zones(text: str) -> list[str]:
    return list(set(_ZONE_PATTERN.findall(text)))


def _extract_tags(text: str, title: str) -> list[str]:
    """提取关键词标签"""
    all_severities = [kw for kws in _SEVERITY_KEYWORDS.values() for kw in kws]
    found = [kw for kw in all_severities if kw in text or kw in title]
    return list(set(found))[:8]  # 最多8个标签


# ─────────────────────────────────────────────────────────────────
# 结构感知分割器
# ─────────────────────────────────────────────────────────────────

class StructureAwareChunker:
    """基于 Markdown 标题层级的结构感知切片器"""

    def __init__(
        self,
        max_chars: int = 1200,
        min_chars: int = 80,
        overlap_chars: int = 150,
    ):
        self.max_chars = max_chars
        self.min_chars = min_chars
        self.overlap_chars = overlap_chars

    def chunk_document(
        self,
        content: str,
        file_ref: str,
        doc_title: str,
    ) -> list[dict[str, Any]]:
        """
        将一份 Markdown 文档切成若干结构感知片段。

        Returns:
            list of dict: {"text": str, "section_path": str, "breadcrumb": str}
        """
        # ─ Step 1: 找所有标题位置
        headers_positions: list[tuple[int, int, str]] = []  # (start, level, title)
        for m in _HEADER_RE.finditer(content):
            level = len(m.group(1))
            title = m.group(2).strip()
            headers_positions.append((m.start(), level, title))

        if not headers_positions:
            # 无标题文档，整体作为一个 chunk（必要时二次分割）
            return self._split_long_text(content, doc_title, doc_title)

        # ─ Step 2: 按标题边界切割文本段落
        sections: list[dict[str, Any]] = []
        header_stack: list[tuple[int, str]] = []  # (level, title)

        for idx, (pos, level, title) in enumerate(headers_positions):
            # 当前段落结束位置
            end_pos = headers_positions[idx + 1][0] if idx + 1 < len(headers_positions) else len(content)
            section_text = content[pos:end_pos].strip()

            # 维护面包屑路径
            # 弹出所有 level >= 当前 level 的历史标题
            while header_stack and header_stack[-1][0] >= level:
                header_stack.pop()
            header_stack.append((level, title))
            breadcrumb = " > ".join(t for _, t in header_stack)

            sections.append({
                "text": section_text,
                "section_path": breadcrumb,
                "breadcrumb": breadcrumb,
                "level": level,
                "title": title,
            })

        # ─ Step 3: 合并过短段落，拆分过长段落
        result: list[dict[str, Any]] = []
        buffer_text = ""
        buffer_path = ""

        for sec in sections:
            text = sec["text"]
            path = sec["section_path"]

            # 与缓冲区合并
            combined = (buffer_text + "\n\n" + text).strip() if buffer_text else text
            if len(combined) < self.min_chars:
                # 太短，先缓冲
                buffer_text = combined
                buffer_path = path
                continue

            # 先把缓冲区刷出
            if buffer_text and len(buffer_text) >= self.min_chars:
                result.extend(self._split_long_text(buffer_text, buffer_path, doc_title))
            buffer_text = ""
            buffer_path = ""

            # 处理当前段落
            result.extend(self._split_long_text(text, path, doc_title))

        # 刷缓冲区尾部
        if buffer_text:
            result.extend(self._split_long_text(buffer_text, buffer_path, doc_title))

        return result

    def _split_long_text(
        self,
        text: str,
        section_path: str,
        doc_title: str,
    ) -> list[dict[str, Any]]:
        """若文本超过 max_chars，按段落进一步切割（带 overlap）"""
        if len(text) <= self.max_chars:
            return [{"text": text, "section_path": section_path, "breadcrumb": section_path}]

        # 按双换行分段落
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
        chunks: list[dict[str, Any]] = []
        current = ""

        for para in paragraphs:
            # ── 段落本身超长：先强制字符截断 ──
            if len(para) > self.max_chars:
                # 先刷缓冲区
                if current:
                    chunks.extend(self._force_char_split(current, section_path))
                    current = ""
                chunks.extend(self._force_char_split(para, section_path))
                continue

            candidate = (current + "\n\n" + para).strip() if current else para
            if len(candidate) <= self.max_chars:
                current = candidate
            else:
                if current:
                    chunks.append({"text": current, "section_path": section_path, "breadcrumb": section_path})
                    overlap = current[-self.overlap_chars:] if len(current) > self.overlap_chars else current
                    current = (overlap + "\n\n" + para).strip()
                else:
                    chunks.extend(self._force_char_split(para, section_path))
                    current = ""

        if current:
            chunks.append({"text": current, "section_path": section_path, "breadcrumb": section_path})

        return chunks

    def _force_char_split(self, text: str, section_path: str) -> list[dict[str, Any]]:
        """在字符级别强制切割超长文本（带 overlap）"""
        step = self.max_chars - self.overlap_chars
        result = []
        for i in range(0, len(text), step):
            sub = text[i: i + self.max_chars]
            if sub:
                result.append({"text": sub, "section_path": section_path, "breadcrumb": section_path})
        return result


# ─────────────────────────────────────────────────────────────────
# RAG 引擎主类
# ─────────────────────────────────────────────────────────────────

class RAGEngine:
    """
    知识大脑 - Advanced RAG Engine

    职责：
    - 从 docs_dir 扫描 .md 文件
    - 结构感知切片 → 向量化 → 存入 ChromaDB
    - semantic_search() 支持语义 + 元数据过滤
    """

    COLLECTION_NAME = "omni_guard_sop"

    def __init__(
        self,
        docs_dir: Path | None = None,
        chroma_dir: Path | None = None,
        embedding_model: str | None = None,
        chunker: StructureAwareChunker | None = None,
    ):
        self.docs_dir = docs_dir or settings.docs_dir
        self.chroma_dir = chroma_dir or settings.chroma_dir
        self.embedding_model_name = embedding_model or settings.embedding_model
        self.chunker = chunker or StructureAwareChunker()

        # 延迟初始化（测试时可 Mock）
        self._embedding_fn: Any = None
        self._collection: Any = None

    # ── 懒加载 Embedding 函数 ──────────────────────────────────────

    def _get_embedding_fn(self) -> Any:
        if self._embedding_fn is None:
            try:
                # 优先使用 ChromaDB 内置 ONNX 向量函数（不依赖 PyTorch）
                from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
                self._embedding_fn = ONNXMiniLM_L6_V2()
            except Exception:
                # 回退：sentence-transformers（需要 PyTorch）
                from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
                self._embedding_fn = SentenceTransformerEmbeddingFunction(
                    model_name=self.embedding_model_name
                )
        return self._embedding_fn

    # ── 懒加载 ChromaDB Collection ─────────────────────────────────

    def _get_collection(self) -> Any:
        if self._collection is None:
            import chromadb
            self.chroma_dir.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(self.chroma_dir))
            self._collection = client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                embedding_function=self._get_embedding_fn(),
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    # ── 文档扫描 & 切片 ────────────────────────────────────────────

    def load_and_chunk_documents(self) -> list[SOPChunk]:
        """扫描 docs_dir 下所有 .md 文件，进行结构感知切片"""
        md_files = sorted(self.docs_dir.glob("*.md"))
        if not md_files:
            raise FileNotFoundError(f"在 {self.docs_dir} 下未找到 .md 文件")

        all_chunks: list[SOPChunk] = []
        for md_path in md_files:
            content = md_path.read_text(encoding="utf-8")
            doc_title = self._extract_title(content, md_path.name)
            raw_chunks = self.chunker.chunk_document(content, md_path.name, doc_title)
            for raw in raw_chunks:
                text = raw["text"]
                section_path = raw["section_path"]
                chunk = SOPChunk(
                    content=text,
                    metadata=ChunkMetadata(
                        file_ref=md_path.name,
                        doc_title=doc_title,
                        section_path=section_path,
                        severity=_infer_severity(text),
                        zone_ids=_extract_zones(text),
                        tags=_extract_tags(text, section_path),
                    ),
                )
                all_chunks.append(chunk)
        return all_chunks

    @staticmethod
    def _extract_title(content: str, fallback: str) -> str:
        """从 Markdown 内容提取第一个一级标题"""
        m = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        return m.group(1).strip() if m else fallback

    # ── 向量化入库 ─────────────────────────────────────────────────

    def build_index(self, force_rebuild: bool = False) -> int:
        """
        将知识库文档向量化并存入 ChromaDB。

        Args:
            force_rebuild: 如为 True，先清空再重建；否则跳过已存在的

        Returns:
            int: 本次新增 chunk 数量
        """
        collection = self._get_collection()

        if force_rebuild:
            # 清空集合
            existing = collection.get()
            if existing["ids"]:
                collection.delete(ids=existing["ids"])

        chunks = self.load_and_chunk_documents()
        existing_ids = set(collection.get()["ids"])

        to_add_ids: list[str] = []
        to_add_docs: list[str] = []
        to_add_metas: list[dict] = []

        for chunk in chunks:
            if chunk.chunk_id in existing_ids:
                continue
            to_add_ids.append(chunk.chunk_id)
            to_add_docs.append(chunk.content)
            to_add_metas.append({
                "file_ref":     chunk.metadata.file_ref,
                "doc_title":    chunk.metadata.doc_title,
                "section_path": chunk.metadata.section_path,
                "severity":     chunk.metadata.severity.value,
                "zone_ids":     ",".join(chunk.metadata.zone_ids),
                "tags":         ",".join(chunk.metadata.tags),
            })

        if to_add_ids:
            # ChromaDB 批量上限约 5000，分批写入
            batch_size = 500
            for i in range(0, len(to_add_ids), batch_size):
                collection.add(
                    ids=to_add_ids[i: i + batch_size],
                    documents=to_add_docs[i: i + batch_size],
                    metadatas=to_add_metas[i: i + batch_size],
                )

        return len(to_add_ids)

    # ── 语义检索 ──────────────────────────────────────────────────

    def semantic_search(
        self,
        query: str,
        top_k: int = 5,
        zone_id: str | None = None,
        severity: SeverityLevel | str | None = None,
        tags: list[str] | None = None,
    ) -> list[SOPChunk]:
        """
        语义检索，支持元数据过滤。

        Args:
            query:    自然语言查询，如"盐雾浓度超标怎么处理"
            top_k:    返回最相关 chunk 数量
            zone_id:  按区域过滤，如 "ZONE-E"
            severity: 按等级过滤（LOW/MEDIUM/HIGH/CRITICAL）
            tags:     必须包含的标签（任意一个命中即可）

        Returns:
            list of SOPChunk, 按相关度降序
        """
        collection = self._get_collection()

        # 构建 ChromaDB where 过滤条件
        where: dict[str, Any] = {}
        if zone_id:
            where["zone_ids"] = {"$contains": zone_id}
        if severity:
            sv = severity.value if isinstance(severity, SeverityLevel) else severity
            where["severity"] = sv

        query_kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": min(top_k, collection.count() or 1),
        }
        if where:
            query_kwargs["where"] = where

        results = collection.query(**query_kwargs)

        chunks: list[SOPChunk] = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]

        for cid, doc, meta in zip(ids, docs, metas):
            # 标签过滤（ChromaDB $contains 仅对精确子串；tags 二次过滤）
            if tags:
                chunk_tags = meta.get("tags", "").split(",")
                if not any(t in chunk_tags for t in tags):
                    continue

            chunk = SOPChunk(
                chunk_id=cid,
                content=doc,
                metadata=ChunkMetadata(
                    file_ref=meta.get("file_ref", ""),
                    doc_title=meta.get("doc_title", ""),
                    section_path=meta.get("section_path", ""),
                    severity=SeverityLevel(meta.get("severity", "MEDIUM")),
                    zone_ids=meta.get("zone_ids", "").split(",") if meta.get("zone_ids") else [],
                    tags=meta.get("tags", "").split(",") if meta.get("tags") else [],
                ),
            )
            chunks.append(chunk)

        return chunks

    # ── 工具方法 ──────────────────────────────────────────────────

    def count(self) -> int:
        """返回当前向量库中的 chunk 总数"""
        return self._get_collection().count()
