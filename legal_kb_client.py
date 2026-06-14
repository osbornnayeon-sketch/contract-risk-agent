"""Legal knowledge-base API adapter using only the Python standard library."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request


def load_dotenv_file(path: Path | None = None) -> None:
    """Load simple KEY=VALUE pairs from .env without overriding existing variables."""
    env_path = path or Path(__file__).with_name(".env")
    if not env_path.exists():
        return
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip().strip('"').strip("'")
        os.environ[key] = value


load_dotenv_file()


@dataclass
class LegalKnowledgeBaseResult:
    cases: list[dict[str, Any]] = field(default_factory=list)
    analysis: dict[str, Any] = field(default_factory=dict)
    notice: str = ""
    provider: str = "local"


class LegalKnowledgeBaseClient:
    """Supports generic search APIs and OpenAI-compatible RAG/chat APIs."""

    def __init__(self) -> None:
        self.url = os.environ.get("LEGAL_KB_API_URL", "https://api.openai.com/v1/chat/completions").strip()
        self.key = os.environ.get("LEGAL_KB_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
        self.key = self.key.strip()
        self.key_header = os.environ.get("LEGAL_KB_API_KEY_HEADER", "Authorization").strip() or "Authorization"
        self.mode = os.environ.get("LEGAL_KB_API_MODE", "openai-compatible").strip().lower().replace("_", "-")
        self.model = os.environ.get("LEGAL_KB_MODEL") or os.environ.get("OPENAI_MODEL", "gpt-4.1")
        self.model = self.model.strip()
        self.timeout = float(os.environ.get("LEGAL_KB_TIMEOUT", "15"))
        self.top_k = int(os.environ.get("LEGAL_KB_TOP_K", "10"))
        self.mock_file = os.environ.get("LEGAL_KB_MOCK_FILE", "").strip()
        self.deep_analysis = os.environ.get("LEGAL_KB_DEEP_ANALYSIS", "1").strip().lower() not in {"0", "false", "no", "off"}
        self.reasoning_effort = os.environ.get("LEGAL_KB_REASONING_EFFORT", "").strip().lower()
        self.extra_headers = self._load_extra_headers()

    @property
    def enabled(self) -> bool:
        return bool(self.mock_file or (self.url and self.key))

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "provider": "mock" if self.mock_file else ("ai-analysis" if self.enabled else "local-only"),
            "model": self.model,
            "top_k": self.top_k,
            "deep_analysis": self.deep_analysis and self.mode == "openai-compatible",
            "message": "AI 案情理解已配置" if self.enabled else "AI 案情理解未启用，当前使用本地规则和案例库",
        }

    def analyze(self, payload: dict[str, Any]) -> LegalKnowledgeBaseResult:
        """Ask an OpenAI-compatible legal model to deeply analyze cause and keywords."""
        if self.mock_file:
            try:
                data = json.loads(Path(self.mock_file).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                return LegalKnowledgeBaseResult(notice=f"AI 模拟分析文件读取失败：{exc}", provider="mock")
            result = self._normalize_response(data, "mock")
            result.cases = []
            if result.analysis:
                result.notice = "已使用模拟 AI 结果理解案情。"
            return result

        if not (self.enabled and self.deep_analysis and self.mode == "openai-compatible"):
            return LegalKnowledgeBaseResult(provider="local")

        request = urllib.request.Request(
            self.url,
            data=json.dumps(self._openai_analysis_payload(payload), ensure_ascii=False).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            return LegalKnowledgeBaseResult(notice=f"AI 深度案情分析返回 HTTP {exc.code}：{detail}")
        except urllib.error.URLError as exc:
            return LegalKnowledgeBaseResult(notice=f"AI 深度案情分析连接失败：{exc.reason}")
        except TimeoutError:
            return LegalKnowledgeBaseResult(notice="AI 深度案情分析请求超时。")
        except json.JSONDecodeError:
            return LegalKnowledgeBaseResult(notice="AI 深度案情分析返回内容不是合法 JSON。")
        except OSError as exc:
            return LegalKnowledgeBaseResult(notice=f"AI 深度案情分析请求失败：{exc}")

        result = self._normalize_response(data, "legal-kb-ai-analysis")
        if result.analysis:
            result.notice = "已使用 AI 深度分析案由、争议焦点和检索关键词。"
        return result

    def search(self, payload: dict[str, Any]) -> LegalKnowledgeBaseResult:
        if self.mock_file:
            try:
                data = json.loads(Path(self.mock_file).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                return LegalKnowledgeBaseResult(notice=f"法律知识库模拟文件读取失败：{exc}", provider="mock")
            return self._normalize_response(data, "mock")

        if not self.url:
            return LegalKnowledgeBaseResult(notice="未配置 LEGAL_KB_API_URL，当前仅使用本地案例库。")

        request_payload = self._openai_payload(payload) if self.mode == "openai-compatible" else payload
        request = urllib.request.Request(
            self.url,
            data=json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            return LegalKnowledgeBaseResult(notice=f"法律知识库 API 返回 HTTP {exc.code}：{detail}")
        except urllib.error.URLError as exc:
            return LegalKnowledgeBaseResult(notice=f"法律知识库 API 连接失败：{exc.reason}")
        except TimeoutError:
            return LegalKnowledgeBaseResult(notice="法律知识库 API 请求超时。")
        except json.JSONDecodeError:
            return LegalKnowledgeBaseResult(notice="法律知识库 API 返回内容不是合法 JSON。")
        except OSError as exc:
            return LegalKnowledgeBaseResult(notice=f"法律知识库 API 请求失败：{exc}")
        return self._normalize_response(data, "legal-kb-api")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        headers.update(self.extra_headers)
        if self.key:
            headers[self.key_header] = f"Bearer {self.key}" if self.key_header.lower() == "authorization" else self.key
        return headers

    def _load_extra_headers(self) -> dict[str, str]:
        raw = os.environ.get("LEGAL_KB_EXTRA_HEADERS", "").strip()
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return {str(key): str(value) for key, value in data.items()} if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _openai_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        prompt = f"""你是类案检索与法律学习助手。请依据已连接的法律知识库检索真实相关案例。
请先对用户案情进行深入法律分析，再据此检索案例。不要沿用初步案由或关键词中与案情不符的内容。
只输出 JSON 对象，不要输出 Markdown。JSON 必须包含 analysis 和 cases：
- analysis: cause, domain, behaviors, subjects, liabilities, legal_elements, issues, query_terms
- cases: 最多 {self.top_k} 个案例，每个包含 title, docket, court, date, cause, domain, facts,
  holding, reasoning, result, tags, support_for, quote, source
无法核验的信息请留空，不得虚构案号、法院或裁判结论。

用户案情：{payload.get("raw_text", "")}
初步案由：{payload.get("cause", "")}
初步争议焦点：{json.dumps(payload.get("issues", []), ensure_ascii=False)}
检索关键词：{json.dumps(payload.get("keywords", []), ensure_ascii=False)}
"""
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "使用法律知识库进行可核验的类案检索。先独立分析案情，再严格输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            **self._reasoning_options(),
        }

    def _openai_analysis_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        prompt = f"""你是中国法类案检索助手。请对用户输入的案情做深度法律分析，用于后续匹配案例。
要求：
1. 只根据用户案情判断，不要被初步规则解析误导。
2. 区分案由、法律领域、主体、行为性质、责任类型、损害类型和争议焦点。
3. 关键词要服务于类案检索，优先输出法律概念、核心事实要素和可替换检索词。
4. 如可能存在多个案由，用“ / ”并列，但把最贴近案情的放在最前。
5. 只输出 JSON 对象，不要输出 Markdown。

JSON 字段：
analysis: {{
  "cause": "建议案由",
  "domain": "法律领域",
  "behaviors": ["行为关键词"],
  "subjects": ["主体"],
  "liabilities": ["责任类型"],
  "legal_elements": {{"行为性质": [], "责任主体": [], "责任类型": [], "损害类型": []}},
  "issues": ["争议焦点"],
  "query_terms": ["检索关键词"]
}}

用户案情：{payload.get("raw_text", "")}
规则初步案由：{payload.get("cause", "")}
规则初步领域：{payload.get("domain", "")}
规则初步争议焦点：{json.dumps(payload.get("issues", []), ensure_ascii=False)}
规则初步关键词：{json.dumps(payload.get("keywords", []), ensure_ascii=False)}
"""
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "独立完成案情解析、案由识别和检索词生成，并严格输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.05,
            "response_format": {"type": "json_object"},
            **self._reasoning_options(),
        }

    def _reasoning_options(self) -> dict[str, Any]:
        if self.reasoning_effort not in {"minimal", "low", "medium", "high"}:
            return {}
        return {"reasoning_effort": self.reasoning_effort}

    def _normalize_response(self, data: Any, provider: str) -> LegalKnowledgeBaseResult:
        if self.mode == "openai-compatible" and isinstance(data, dict):
            choices = data.get("choices")
            if isinstance(choices, list) and choices:
                content = ((choices[0].get("message") or {}).get("content")) if isinstance(choices[0], dict) else None
                if isinstance(content, str):
                    cleaned = content.strip()
                    if cleaned.startswith("```"):
                        cleaned = cleaned.strip("`").strip()
                        if cleaned.lower().startswith("json"):
                            cleaned = cleaned[4:].strip()
                    try:
                        data = json.loads(cleaned)
                    except json.JSONDecodeError:
                        return LegalKnowledgeBaseResult(notice="法律知识库模型未返回合法 JSON。", provider=provider)

        cases = self._extract_records(data)
        analysis = self._extract_analysis(data)
        if not cases:
            return LegalKnowledgeBaseResult(
                analysis=analysis,
                notice="法律知识库 API 已响应，但未返回可识别的案例列表。",
                provider=provider,
            )
        return LegalKnowledgeBaseResult(
            cases=cases[: self.top_k],
            analysis=analysis,
            notice=f"已从法律知识库 API 读取 {min(len(cases), self.top_k)} 条候选案例。",
            provider=provider,
        )

    @staticmethod
    def _extract_records(data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if not isinstance(data, dict):
            return []
        for key in ("results", "cases", "items", "records", "documents", "list"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        nested = data.get("data")
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
        if isinstance(nested, dict):
            return LegalKnowledgeBaseClient._extract_records(nested)
        return []

    @staticmethod
    def _extract_analysis(data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            return {}
        analysis = data.get("analysis") or data.get("parsed") or data.get("case_analysis")
        if isinstance(analysis, dict):
            return analysis
        nested = data.get("data")
        if isinstance(nested, dict):
            analysis = nested.get("analysis") or nested.get("parsed")
            return analysis if isinstance(analysis, dict) else {}
        return {}
