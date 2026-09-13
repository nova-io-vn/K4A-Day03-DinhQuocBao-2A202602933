"""CLI chạy Chatbot/ReAct Agent VinBus và xuất Waterfall Trace Log."""

import json
import os
import sys
import time
from typing import Any, Dict, List

from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from mcp_server import MCPVinBusServer
from prompts import CHATBOT_BASELINE_PROMPT, MAX_ITERATIONS, REACT_AGENT_SYSTEM_PROMPT
from providers import BaseLLMProvider, LLMProviderError, get_llm_provider

load_dotenv()
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_test_cases() -> List[Dict[str, Any]]:
    """Đọc đúng bộ test cá nhân hóa; không âm thầm dùng file mẫu."""
    path = os.path.join(BASE_DIR, "config", "test_cases.json")
    if not os.path.exists(path):
        raise FileNotFoundError("Thiếu config/test_cases.json.")
    with open(path, "r", encoding="utf-8") as file:
        tests = json.load(file)
    if len(tests) != 5:
        raise ValueError(f"Bộ nghiệm thu phải có đúng 5 test cases, hiện có {len(tests)}.")
    return tests


def save_waterfall_trace(trace_data: List[Dict[str, Any]]) -> str:
    """Ghi UTF-8 Waterfall Trace Log và trả về đường dẫn file."""
    trace_path = os.path.join(BASE_DIR, "docs", "trace_waterfall.json")
    with open(trace_path, "w", encoding="utf-8") as file:
        json.dump(trace_data, file, ensure_ascii=False, indent=2)
        file.write("\n")
    print(f"📊 Đã lưu {len(trace_data)} sự kiện tại '{trace_path}'.")
    return trace_path


def run_baseline_chatbot(user_query: str, provider: BaseLLMProvider) -> str:
    print(f"\n💬 [CHATBOT BASELINE] {user_query}")
    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    print(f"🤖 {response}")
    return response


def _iteration_prompt(user_query: str, observations: List[Dict[str, Any]]) -> str:
    if not observations:
        return user_query
    history = json.dumps(observations, ensure_ascii=False, indent=2)
    return (
        f"YÊU CẦU GỐC:\n{user_query}\n\n"
        f"OBSERVATION ĐÃ NHẬN (không gọi lại cùng tool và tham số):\n{history}\n\n"
        "Hãy tiếp tục hoàn thành yêu cầu gốc. Nếu cần thêm hành động, gọi đúng một tool tiếp theo; "
        "nếu đã đủ dữ liệu hoặc có lỗi chặn luồng, hãy trả lời cuối cùng dựa đúng trên Observation."
    )


def _provider_metadata(provider: BaseLLMProvider) -> Dict[str, Any]:
    return {
        "provider": provider.__class__.__name__,
        "model": provider.model_name,
        "live_api": provider.is_live,
    }


def run_react_agent(
    user_query: str,
    provider: BaseLLMProvider,
    mcp_server: MCPVinBusServer,
) -> List[Dict[str, Any]]:
    """Chạy ReAct loop thật sự: mỗi Observation được nạp vào lượt LLM kế tiếp."""
    print(f"\n🤖 [REACT AGENT] {user_query}")
    trace_logs: List[Dict[str, Any]] = []
    observations: List[Dict[str, Any]] = []
    called_signatures = set()
    metadata = _provider_metadata(provider)

    for step in range(1, MAX_ITERATIONS + 1):
        print(f"\n--- 🔄 ReAct Step {step}/{MAX_ITERATIONS} ---")
        llm_started = time.perf_counter()
        try:
            llm_response = provider.generate_with_tools(
                _iteration_prompt(user_query, observations),
                mcp_server.list_tools(),
                system_prompt=REACT_AGENT_SYSTEM_PROMPT,
            )
        except LLMProviderError as exc:
            latency_ms = round((time.perf_counter() - llm_started) * 1000, 2)
            error_event = {
                "step": step,
                "query": user_query,
                "action_type": "LLM_ERROR",
                "error": str(exc),
                "latency_ms": latency_ms,
                **metadata,
            }
            trace_logs.append(error_event)
            print(f"❌ {exc}")
            break

        llm_latency_ms = round((time.perf_counter() - llm_started) * 1000, 2)
        thought = llm_response.get("thought", "Đang chọn hành động tiếp theo.")
        print(f"🧠 [Thought summary] {thought}")

        if llm_response.get("type") == "text":
            final_content = llm_response.get("content", "").strip()
            print(f"🏁 [Final Answer] {final_content}")
            trace_logs.append(
                {
                    "step": step,
                    "query": user_query,
                    "action_type": "FINAL_ANSWER",
                    "thought": thought,
                    "output": final_content,
                    "latency_ms": llm_latency_ms,
                    **metadata,
                }
            )
            break

        if llm_response.get("type") != "tool_call":
            trace_logs.append(
                {
                    "step": step,
                    "query": user_query,
                    "action_type": "AGENT_PROTOCOL_ERROR",
                    "error": f"Loại phản hồi không hợp lệ: {llm_response.get('type')!r}",
                    "latency_ms": llm_latency_ms,
                    **metadata,
                }
            )
            break

        tool_name = llm_response.get("tool_name", "")
        arguments = llm_response.get("arguments", {})
        signature = json.dumps([tool_name, arguments], ensure_ascii=False, sort_keys=True)
        if signature in called_signatures:
            print("⚠️ Phát hiện tool call trùng lặp; dừng để tránh vòng lặp vô hạn.")
            trace_logs.append(
                {
                    "step": step,
                    "query": user_query,
                    "action_type": "DUPLICATE_TOOL_CALL_BLOCKED",
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "latency_ms": llm_latency_ms,
                    **metadata,
                }
            )
            break
        called_signatures.add(signature)

        print(f"🛠️ [Action] {tool_name}({arguments})")
        mcp_started = time.perf_counter()
        mcp_response = mcp_server.call_tool(tool_name, arguments)
        mcp_latency_ms = round((time.perf_counter() - mcp_started) * 1000, 2)
        observation = mcp_response.get("result", {})
        print(f"👁️ [Observation] {json.dumps(observation, ensure_ascii=False)}")

        observations.append(
            {"tool_name": tool_name, "arguments": arguments, "result": observation}
        )
        trace_logs.append(
            {
                "step": step,
                "query": user_query,
                "action_type": "TOOL_EXECUTION",
                "thought": thought,
                "tool_name": tool_name,
                "arguments": arguments,
                "observation": observation,
                "llm_latency_ms": llm_latency_ms,
                "mcp_latency_ms": mcp_latency_ms,
                "latency_ms": round(llm_latency_ms + mcp_latency_ms, 2),
                "jsonrpc": mcp_response.get("jsonrpc"),
                "mcp_server": mcp_response.get("server"),
                **metadata,
            }
        )
    else:
        trace_logs.append(
            {
                "step": MAX_ITERATIONS + 1,
                "query": user_query,
                "action_type": "MAX_ITERATIONS_REACHED",
                "error": "Agent chưa tạo câu trả lời cuối cùng trong giới hạn vòng lặp.",
                **metadata,
            }
        )

    return trace_logs


def evaluate_trace(test_case: Dict[str, Any], trace: List[Dict[str, Any]]) -> tuple[bool, str]:
    """Chấm hành vi quan sát được: chuỗi tool và sự tồn tại của final answer."""
    actual_tools = [event["tool_name"] for event in trace if event["action_type"] == "TOOL_EXECUTION"]
    expected_tools = test_case.get("expected_tools", [])
    has_final = any(event["action_type"] == "FINAL_ANSWER" for event in trace)
    if actual_tools != expected_tools:
        return False, f"expected_tools={expected_tools}, actual_tools={actual_tools}"
    if not has_final:
        return False, "Agent không tạo FINAL_ANSWER."
    return True, "Đúng chuỗi tool và có FINAL_ANSWER."


def run_test_suite(provider: BaseLLMProvider, mcp_server: MCPVinBusServer) -> bool:
    tests = load_test_cases()
    all_traces: List[Dict[str, Any]] = []
    passed_count = 0

    print(f"🚀 Chạy {len(tests)} test cases với {provider.__class__.__name__}/{provider.model_name}")
    for test_case in tests:
        print("\n" + "=" * 66)
        print(f"🧪 [{test_case['id']}] {test_case['type']} ({test_case['complexity']})")
        print(f"📌 Kỳ vọng: {test_case['expected_behavior']}")
        trace = run_react_agent(test_case["question"], provider, mcp_server)
        for event in trace:
            event["test_case_id"] = test_case["id"]
        all_traces.extend(trace)

        passed, reason = evaluate_trace(test_case, trace)
        test_case["actual_result"] = "PASS" if passed else "FAIL"
        test_case["evaluation_note"] = reason
        print(f"{'✅ PASS' if passed else '❌ FAIL'}: {reason}")
        passed_count += int(passed)

    save_waterfall_trace(all_traces)
    print("\n" + "=" * 66)
    print(f"📊 KẾT QUẢ: {passed_count}/{len(tests)} test cases PASS")
    tool_calls = sum(event["action_type"] == "TOOL_EXECUTION" for event in all_traces)
    print(f"🛠️ Tổng số tool calls qua MCP: {tool_calls}")
    print(f"🔌 Live API: {provider.is_live}")
    return passed_count == len(tests)


def main() -> int:
    print("=" * 66)
    print("VINUNI DAY 03 LAB - VINBUS REACT AGENT")
    print("=" * 66)
    try:
        provider = get_llm_provider()
        mcp_server = MCPVinBusServer()
    except (ValueError, FileNotFoundError) as exc:
        print(f"❌ Cấu hình không hợp lệ: {exc}")
        return 2

    print(f"🔌 Provider: {provider.__class__.__name__} | Model: {provider.model_name}")
    print(f"🌐 MCP Server: {mcp_server.server_name}")

    if "--all" in sys.argv:
        return 0 if run_test_suite(provider, mcp_server) else 1
    if "--interactive" in sys.argv:
        print("Gõ 'exit' hoặc 'quit' để kết thúc.")
        while True:
            try:
                user_input = input("\n👤 Bạn: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\n👋 Đã thoát.")
                return 0
            if not user_input or user_input.lower() in {"exit", "quit"}:
                print("👋 Đã thoát.")
                return 0
            save_waterfall_trace(run_react_agent(user_input, provider, mcp_server))

    print("Cách dùng:")
    print("  python src/app.py --all          # chạy 5 test cases")
    print("  python src/app.py --interactive  # trò chuyện trực tiếp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
