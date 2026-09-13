"""MCP-style JSON-RPC server cho các công cụ VinBus của bài lab."""

import json
import sys
from typing import Any, Dict, List

from tools import TOOLS_SCHEMA, dispatch_tool_call

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


class MCPVinBusServer:
    """Công bố tool schemas và đóng gói kết quả theo JSON-RPC 2.0."""

    def __init__(self, server_name: str = "vinbus-customer-service-mcp-server"):
        self.server_name = server_name
        self.version = "2026.1.0"

    def list_tools(self) -> List[Dict[str, Any]]:
        return TOOLS_SCHEMA

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Thực thi một tool và trả về response envelope JSON-RPC 2.0."""
        try:
            content = json.loads(dispatch_tool_call(tool_name, arguments))
        except json.JSONDecodeError as exc:
            content = {
                "status": "INVALID_TOOL_RESPONSE",
                "error": f"Tool trả về JSON không hợp lệ: {exc}",
            }

        return {
            "jsonrpc": "2.0",
            "server": self.server_name,
            "tool": tool_name,
            "result": content,
        }


# Alias giúp các đoạn mã tham khảo cũ vẫn import được mà không ảnh hưởng chủ đề mới.
MCPAcademicServer = MCPVinBusServer


if __name__ == "__main__":
    print("=" * 66)
    print("KIỂM THỬ MCP SERVER VINBUS")
    print("=" * 66)
    server = MCPVinBusServer()
    tools = server.list_tools()
    print(f"✅ Server: {server.server_name} (Version: {server.version})")
    print(f"📦 Số lượng tools công bố: {len(tools)}")
    print(f"📋 Tools: {', '.join(tool['name'] for tool in tools)}")

    test_result = server.call_tool("lookup_bus_route", {"route_code": "E01"})
    print("✅ JSON-RPC dispatch lookup_bus_route thành công:")
    print(json.dumps(test_result, ensure_ascii=False, indent=2))
