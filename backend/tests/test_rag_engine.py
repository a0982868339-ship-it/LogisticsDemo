"""
tests/test_rag_engine.py — T3 RAG引擎单元测试

测试策略：
- StructureAwareChunker 不依赖任何外部服务，可直接测试
- RAGEngine 的向量化/检索部分通过 Mock ChromaDB 进行隔离测试
"""
from __future__ import annotations

import re
import sys
import types
import unittest.mock as mock
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ─────────────────────────────────────────────────────────────────
# 测试夹具（Fixtures）
# ─────────────────────────────────────────────────────────────────

SAMPLE_MARKDOWN = """# 异常货物处置标准操作程序

**文件编号：** SYZBQ-OPM-006  
**版本号：** V2.8.0

## 1. 目的

规范当巡检机器人或人工复核发现疑似异常货物后，园区各部门的处置工作流程，确保在符合法律法规要求的前提下，及时、规范地处置异常货物。

## 2. 异常货物类型与分级

### 2.1 异常类型分类

P0级别告警：禁止进口商品，立即紧急响应，切断危险源。

| 异常代码 | 异常类型 | 常见表现 | 初始告警等级 |
|---|---|---|---|
| ANO-01 | 品类不符 | AI识别品类与申报不一致，差异≥25% | P1 |
| ANO-05 | 禁止进口商品 | 命中禁刀/禁烟/管制品清单 | P0 |
| ANO-08 | 危化品泄漏 | 气体检测超阈值+热成像异常 | P0 |

### 2.2 处置优先级矩阵

P0告警等级：当班调度员响应时限立即（≤1分钟），合规审计员介入时限≤5分钟，海关驻场通报时限立即（电话+系统推送）。
P1告警等级：当班调度员响应时限≤3分钟，合规审计员介入时限≤15分钟。

## 3. 标准处置流程

### 3.1 P0级异常货物处置流程

适用于禁止进口商品、危化品泄漏、濒危物品。

STEP 1 — 触发告警：EMIS系统自动设定该货物所在库位5m半径为临时禁区，机器人驻留现场，持续拍摄。
STEP 2 — 内部响应：调度员确认告警有效性，通知安全消防大队，对ANO-08启动危化品响应小队。
STEP 3 — 现场处置：危化品响应小队全套防护进场，启动应急通风，必要时疏散周边100m人员。

适用区域：ZONE-E、ZONE-A、HZ-A、HZ-B

## 4. 法律依据

《危险化学品安全管理条例》（国务院令第591号）第三章第69-78条。
《海关行政处罚实施条例》（国务院令第420号）第7-16条。
"""

SHORT_MARKDOWN = """# 简短文档

## 1. 概述

内容很短。

## 2. 结论

同上。
"""

LONG_SECTION_MARKDOWN = """# 长段落文档

## 超长章节

""" + ("这是一段非常非常非常长的内容，用于测试超长段落的拆分逻辑。" * 60)


# ─────────────────────────────────────────────────────────────────
# StructureAwareChunker 测试
# ─────────────────────────────────────────────────────────────────

class TestStructureAwareChunker:
    @pytest.fixture
    def chunker(self):
        from app.core.rag_engine import StructureAwareChunker
        return StructureAwareChunker(max_chars=1200, min_chars=50, overlap_chars=150)

    def test_produces_multiple_chunks_from_rich_doc(self, chunker):
        chunks = chunker.chunk_document(SAMPLE_MARKDOWN, "06_test.md", "异常货物处置标准操作程序")
        assert len(chunks) >= 3, "富文本文档应产生至少3个chunk"

    def test_each_chunk_within_max_chars(self, chunker):
        chunks = chunker.chunk_document(SAMPLE_MARKDOWN, "06_test.md", "异常货物处置标准操作程序")
        for ch in chunks:
            assert len(ch["text"]) <= chunker.max_chars + 50, (
                f"chunk 超过 max_chars: {len(ch['text'])} chars"
            )

    def test_section_path_contains_breadcrumb(self, chunker):
        chunks = chunker.chunk_document(SAMPLE_MARKDOWN, "06_test.md", "异常货物处置标准操作程序")
        # 多级标题的 chunk 应包含父级标题
        paths = [ch["section_path"] for ch in chunks]
        # 至少有一个路径包含 " > " 分隔符（表示是子级章节）
        nested = [p for p in paths if " > " in p]
        assert len(nested) > 0, f"应存在嵌套路径，实际路径: {paths}"

    def test_short_sections_are_merged(self, chunker):
        """过短的章节（< min_chars）应与邻近章节合并，不单独成chunk"""
        chunks = chunker.chunk_document(SHORT_MARKDOWN, "short.md", "简短文档")
        # 短文档的2个小章节应被合并为尽可能少的chunk
        assert len(chunks) <= 2

    def test_long_section_is_split(self, chunker):
        """超过 max_chars 的段落应被拆分"""
        chunks = chunker.chunk_document(LONG_SECTION_MARKDOWN, "long.md", "长段落文档")
        assert len(chunks) >= 2, "超长段落应被拆分为>=2个chunk"
        for ch in chunks:
            assert len(ch["text"]) <= chunker.max_chars + 50

    def test_no_document_no_headers_handled(self, chunker):
        """无标题的纯文本应作为整体处理"""
        plain = "这是一段没有任何Markdown标题的纯文本。" * 10
        chunks = chunker.chunk_document(plain, "plain.md", "纯文本")
        assert len(chunks) >= 1
        assert all(ch["text"] for ch in chunks)

    def test_chunk_text_not_empty(self, chunker):
        chunks = chunker.chunk_document(SAMPLE_MARKDOWN, "06_test.md", "doc")
        for ch in chunks:
            assert ch["text"].strip(), "chunk 不应为空"


# ─────────────────────────────────────────────────────────────────
# 元数据提取测试
# ─────────────────────────────────────────────────────────────────

class TestMetadataExtraction:
    def test_infer_severity_critical(self):
        from app.core.rag_engine import _infer_severity
        from app.models.schemas import SeverityLevel
        text = "P0级别：立即禁止所有作业，切断危险源。"
        assert _infer_severity(text) == SeverityLevel.CRITICAL

    def test_infer_severity_high(self):
        from app.core.rag_engine import _infer_severity
        from app.models.schemas import SeverityLevel
        text = "液体泄漏告警，存在危险，注意安全。"
        assert _infer_severity(text) == SeverityLevel.HIGH

    def test_infer_severity_low_default(self):
        from app.core.rag_engine import _infer_severity
        from app.models.schemas import SeverityLevel
        text = "日常记录，建议参考标准流程。"
        assert _infer_severity(text) == SeverityLevel.LOW

    def test_extract_zones(self):
        from app.core.rag_engine import _extract_zones
        text = "适用区域：ZONE-E、ZONE-A、HZ-A、HZ-B，以及BLDG-A03。"
        zones = _extract_zones(text)
        assert "ZONE-E" in zones
        assert "HZ-A" in zones
        assert "BLDG-A03" in zones

    def test_extract_zones_empty(self):
        from app.core.rag_engine import _extract_zones
        text = "本节无特定区域限制。"
        assert _extract_zones(text) == []

    def test_extract_title(self):
        from app.core.rag_engine import RAGEngine
        title = RAGEngine._extract_title(SAMPLE_MARKDOWN, "fallback.md")
        assert title == "异常货物处置标准操作程序"

    def test_extract_title_fallback(self):
        from app.core.rag_engine import RAGEngine
        title = RAGEngine._extract_title("无标题文档", "fallback.md")
        assert title == "fallback.md"


# ─────────────────────────────────────────────────────────────────
# RAGEngine（Mock ChromaDB）测试
# ─────────────────────────────────────────────────────────────────

class TestRAGEngine:
    @pytest.fixture
    def tmp_docs_dir(self, tmp_path: Path) -> Path:
        """创建临时知识库目录，写入示例文档"""
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "06_异常货物处置标准操作程序.md").write_text(SAMPLE_MARKDOWN, encoding="utf-8")
        (docs / "02_机器人规格.md").write_text(
            "# 巡检机器人硬件规格说明书\n\n## 1. 概述\n\n本说明书描述三款巡检机器人的技术参数。机型：海鹰-X7Pro，ZONE-A适用。\n\n"
            "## 2. 电池参数\n\n磷酸铁锂电池，48V/200Ah。低电量告警阈值≤18%。\n",
            encoding="utf-8",
        )
        return docs

    @pytest.fixture
    def engine(self, tmp_docs_dir: Path, tmp_path: Path) -> "RAGEngine":
        from app.core.rag_engine import RAGEngine
        return RAGEngine(
            docs_dir=tmp_docs_dir,
            chroma_dir=tmp_path / "chroma_db",
        )

    def test_load_and_chunk_documents(self, engine):
        chunks = engine.load_and_chunk_documents()
        assert len(chunks) >= 4, f"应至少生成4个chunk，实际:{len(chunks)}"

    def test_chunk_splitting_respects_max_chars(self, engine):
        chunks = engine.load_and_chunk_documents()
        for ch in chunks:
            assert ch.char_count <= 1400, f"chunk 超限: {ch.char_count} chars"

    def test_metadata_file_ref_correct(self, engine):
        chunks = engine.load_and_chunk_documents()
        file_refs = {ch.metadata.file_ref for ch in chunks}
        assert "06_异常货物处置标准操作程序.md" in file_refs
        assert "02_机器人规格.md" in file_refs

    def test_severity_high_in_critical_section(self, engine):
        from app.models.schemas import SeverityLevel
        chunks = engine.load_and_chunk_documents()
        # 包含 P0 关键词的 chunk 应推断为 CRITICAL
        critical_chunks = [
            ch for ch in chunks
            if ch.metadata.severity in (SeverityLevel.CRITICAL, SeverityLevel.HIGH)
        ]
        assert len(critical_chunks) >= 1, "应有至少1个高危chunk"

    def test_zone_extraction(self, engine):
        chunks = engine.load_and_chunk_documents()
        zone_chunks = [ch for ch in chunks if "ZONE-E" in ch.metadata.zone_ids]
        assert len(zone_chunks) >= 1, "应找到含 ZONE-E 的chunk"

    def test_build_index_with_mock_chromadb(self, engine):
        """Mock ChromaDB，不需要实际向量化"""
        mock_collection = MagicMock()
        mock_collection.get.return_value = {"ids": []}
        mock_collection.count.return_value = 0
        engine._collection = mock_collection
        engine._embedding_fn = MagicMock()

        added = engine.build_index()
        assert added >= 4
        assert mock_collection.add.called

    def test_semantic_search_with_mock(self, engine):
        """Mock ChromaDB 查询返回，验证 SOPChunk 正确构建"""
        from app.models.schemas import SeverityLevel

        mock_collection = MagicMock()
        mock_collection.count.return_value = 5
        mock_collection.query.return_value = {
            "ids": [["chunk-001", "chunk-002"]],
            "documents": [
                [
                    "当盐雾浓度超过15mg/m³时，立即停止室外作业，机器人进入1号干燥仓。",
                    "高盐雾环境维护规程：每次作业后用纯水冲洗机器人表面。",
                ]
            ],
            "metadatas": [
                [
                    {
                        "file_ref": "12_维护保养.md",
                        "doc_title": "维护保养手册",
                        "section_path": "3.2 > 高盐雾维护",
                        "severity": "HIGH",
                        "zone_ids": "ZONE-M",
                        "tags": "盐雾,高温",
                    },
                    {
                        "file_ref": "12_维护保养.md",
                        "doc_title": "维护保养手册",
                        "section_path": "3.3 > 清洁规程",
                        "severity": "MEDIUM",
                        "zone_ids": "",
                        "tags": "",
                    },
                ]
            ],
        }
        engine._collection = mock_collection
        engine._embedding_fn = MagicMock()

        results = engine.semantic_search("盐雾浓度超标", top_k=3)
        assert len(results) == 2
        assert results[0].metadata.severity == SeverityLevel.HIGH
        assert results[0].metadata.section_path == "3.2 > 高盐雾维护"
        assert "盐雾" in results[0].content

    def test_search_calls_chromadb_with_where_filter(self, engine):
        """带 zone_id 过滤时，确认 where 参数被传入 ChromaDB"""
        from app.models.schemas import SeverityLevel

        mock_collection = MagicMock()
        mock_collection.count.return_value = 10
        mock_collection.query.return_value = {
            "ids": [[]], "documents": [[]], "metadatas": [[]]
        }
        engine._collection = mock_collection
        engine._embedding_fn = MagicMock()

        engine.semantic_search("危化品泄漏", zone_id="ZONE-E", severity=SeverityLevel.CRITICAL)

        call_kwargs = mock_collection.query.call_args.kwargs
        assert "where" in call_kwargs
        where = call_kwargs["where"]
        assert where.get("severity") == "CRITICAL"
