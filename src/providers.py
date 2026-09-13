"""LLM adapters cho OpenAI, Gemini và chế độ mock offline."""

import json
import os
import re
from typing import Any, Dict, List

from dotenv import load_dotenv

load_dotenv()


class LLMProviderError(RuntimeError):
    """Lỗi gọi live API; không âm thầm biến một lần chạy thật thành mock."""


class BaseLLMProvider:
    is_live = False
    model_name = "unknown"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        raise NotImplementedError

    def generate_with_tools(
        self,
        prompt: str,
        tools_schema: List[Dict[str, Any]],
        system_prompt: str = "",
    ) -> Dict[str, Any]:
        raise NotImplementedError


class MockOfflineProvider(BaseLLMProvider):
    """Mock xác định trước để kiểm tra logic mà không dùng token."""

    model_name = "Offline-Mock-VinBus-2026"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        return "Đây là chatbot minh họa; tôi không có quyền gọi công cụ hoặc dữ liệu vận hành."

    @staticmethod
    def _route_code(text: str) -> str:
        match = re.search(r"\bE\d{2}\b", text, flags=re.IGNORECASE)
        return match.group(0).upper() if match else "E01"

    @staticmethod
    def _registration_args(text: str) -> Dict[str, str]:
        phone = re.search(r"\b0\d{9}\b", text)
        start_date = re.search(r"\b20\d{2}-\d{2}-\d{2}\b", text)
        lowered = text.lower()
        name = "Đinh Quốc Bảo" if "đinh quốc bảo" in lowered else "Trần Minh Anh"
        return {
            "customer_name": name,
            "phone_number": phone.group(0) if phone else "0912345678",
            "route_code": MockOfflineProvider._route_code(text),
            "start_date": start_date.group(0) if start_date else "2026-10-01",
        }

    def generate_with_tools(
        self,
        prompt: str,
        tools_schema: List[Dict[str, Any]],
        system_prompt: str = "",
    ) -> Dict[str, Any]:
        lowered = prompt.lower()
        has_observation = "observation đã nhận" in lowered
        registered = '"register_monthly_pass"' in prompt
        looked_up = '"lookup_bus_route"' in prompt

        if has_observation:
            if "nếu có, đăng ký" in lowered and looked_up and not registered and '"status": "SUCCESS"' in prompt:
                return {
                    "type": "tool_call",
                    "tool_name": "register_monthly_pass",
                    "arguments": self._registration_args(prompt),
                    "thought": "Tuyến đã tồn tại; tiếp tục bước đăng ký vé tháng.",
                }
            return {
                "type": "text",
                "content": "Tôi đã hoàn tất yêu cầu theo Observation từ MCP Server. Kết quả chỉ là dữ liệu mô phỏng Lab 3.",
                "thought": "Đã đủ dữ liệu công cụ để kết luận.",
            }

        if "đăng ký vé tháng" in lowered and "trước tiên" not in lowered:
            return {
                "type": "tool_call",
                "tool_name": "register_monthly_pass",
                "arguments": self._registration_args(prompt),
                "thought": "Yêu cầu có đủ thông tin để đăng ký vé tháng.",
            }
        if any(keyword in lowered for keyword in ("tra cứu", "kiểm tra tuyến", "lộ trình")):
            return {
                "type": "tool_call",
                "tool_name": "lookup_bus_route",
                "arguments": {"route_code": self._route_code(prompt)},
                "thought": "Cần tra cứu dữ liệu tuyến từ MCP Server.",
            }
        return {
            "type": "text",
            "content": (
                "VinBus sử dụng xe buýt điện. Trong bài lab này, tôi có thể tra cứu tuyến "
                "và tạo đăng ký vé tháng trên dữ liệu mô phỏng."
            ),
            "thought": "Câu hỏi chung, không cần gọi công cụ.",
        }


class GeminiProvider(BaseLLMProvider):
    """Google Gemini adapter dùng native function calling."""

    is_live = True

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gemini-2.5-flash"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        try:
            from google import genai

            response = genai.Client(api_key=self.api_key).models.generate_content(
                model=self.model_name,
                contents=f"{system_prompt}\n\n{prompt}" if system_prompt else prompt,
            )
            return response.text or ""
        except Exception as exc:
            raise LLMProviderError(f"Gemini API thất bại: {exc}") from exc

    def generate_with_tools(
        self,
        prompt: str,
        tools_schema: List[Dict[str, Any]],
        system_prompt: str = "",
    ) -> Dict[str, Any]:
        try:
            from google import genai
            from google.genai import types

            declarations = [
                {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool["parameters"],
                }
                for tool in tools_schema
            ]
            config = types.GenerateContentConfig(
                system_instruction=system_prompt or None,
                tools=[{"function_declarations": declarations}],
                temperature=0.1,
            )
            response = genai.Client(api_key=self.api_key).models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )
            if response.function_calls:
                call = response.function_calls[0]
                arguments = dict(call.args) if call.args else {}
                return {
                    "type": "tool_call",
                    "tool_name": call.name,
                    "arguments": arguments,
                    "thought": f"Gemini chọn công cụ {call.name}.",
                }
            return {
                "type": "text",
                "content": response.text or "",
                "thought": "Gemini đã đủ dữ liệu để trả lời trực tiếp.",
            }
        except Exception as exc:
            raise LLMProviderError(f"Gemini API thất bại: {exc}") from exc


class OpenAIProvider(BaseLLMProvider):
    """OpenAI adapter dùng native function calling."""

    is_live = True

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gpt-4o-mini"

    @staticmethod
    def _tools(tools_schema: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool["parameters"],
                },
            }
            for tool in tools_schema
        ]

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        try:
            from openai import OpenAI

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = OpenAI(api_key=self.api_key).chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.1,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            raise LLMProviderError(f"OpenAI API thất bại: {exc}") from exc

    def generate_with_tools(
        self,
        prompt: str,
        tools_schema: List[Dict[str, Any]],
        system_prompt: str = "",
    ) -> Dict[str, Any]:
        try:
            from openai import OpenAI

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = OpenAI(api_key=self.api_key).chat.completions.create(
                model=self.model_name,
                messages=messages,
                tools=self._tools(tools_schema),
                tool_choice="auto",
                temperature=0.1,
            )
            message = response.choices[0].message
            if message.tool_calls:
                call = message.tool_calls[0]
                arguments = json.loads(call.function.arguments or "{}")
                return {
                    "type": "tool_call",
                    "tool_name": call.function.name,
                    "arguments": arguments,
                    "thought": f"OpenAI chọn công cụ {call.function.name}.",
                }
            return {
                "type": "text",
                "content": message.content or "",
                "thought": "OpenAI đã đủ dữ liệu để trả lời trực tiếp.",
            }
        except Exception as exc:
            raise LLMProviderError(f"OpenAI API thất bại: {exc}") from exc


def _is_configured(value: str | None, placeholder: str) -> bool:
    return bool(value and value != placeholder)


def get_llm_provider() -> BaseLLMProvider:
    """Khởi tạo đúng provider; cấu hình live sai sẽ báo lỗi rõ ràng."""
    provider_type = os.getenv("LLM_PROVIDER", "mock").strip().lower()
    if provider_type == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if not _is_configured(key, "your_openai_api_key_here"):
            raise ValueError("LLM_PROVIDER=openai nhưng OPENAI_API_KEY chưa được cấu hình.")
        return OpenAIProvider(api_key=key)
    if provider_type == "gemini":
        key = os.getenv("GEMINI_API_KEY")
        if not _is_configured(key, "your_gemini_api_key_here"):
            raise ValueError("LLM_PROVIDER=gemini nhưng GEMINI_API_KEY chưa được cấu hình.")
        return GeminiProvider(api_key=key)
    if provider_type == "mock":
        return MockOfflineProvider()
    raise ValueError(f"LLM_PROVIDER không được hỗ trợ: {provider_type!r}")
