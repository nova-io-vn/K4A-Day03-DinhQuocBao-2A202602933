# 📊 BÁO CÁO THU HOẠCH NGHIỆM THU BÀI LAB 3

> **Họ và Tên Học viên:** Đinh Quốc Bảo<br>
> **Mã Sinh Viên / Mã Học viên:** 2A202602933<br>
> **Chủ đề Lựa chọn:** Trợ lý Dịch vụ Khách hàng VinBus: Tra cứu lộ trình tuyến xe buýt điện và đăng ký vé tháng.<br>


---

## 1. Agentic Fit Scoring Matrix

| Tiêu chí đánh giá | Điểm (1-5) | Giải trình |
| :--- | :---: | :--- |
| **Multi-step Reasoning** | **5/5** | Một yêu cầu có thể cần tra cứu tuyến, đánh giá kết quả `SUCCESS/NOT_FOUND`, rồi mới quyết định có đăng ký vé tháng hay không. TC04 kiểm chứng chuỗi ba bước này. |
| **Tool Interaction** | **5/5** | Agent phải dùng hai tool qua MCP: `lookup_bus_route` để đọc dữ liệu mô phỏng và `register_monthly_pass` để tạo giao dịch mô phỏng. LLM không thể tự suy đoán kết quả hai thao tác này. |
| **Dynamic Decision** | **5/5** | Hành động đăng ký trong TC04 phụ thuộc trực tiếp vào Observation của bước tra cứu. Nếu tuyến không tồn tại, Agent phải dừng đăng ký và phản hồi theo dữ liệu tool. |
| **Long Horizon Goal** | **4/5** | Agent duy trì mục tiêu gốc qua nhiều vòng Thought → Action → Observation và có bảo vệ chống gọi tool trùng. Phạm vi lab chưa yêu cầu memory dài hạn qua nhiều phiên nên không chấm 5. |
| **TỔNG ĐIỂM AGENTIC FIT** | **19/20** | **Lớn hơn 12/20, rất phù hợp để triển khai Agentic System.** |

## 2. Thiết kế công cụ và MCP

| Tool | Vai trò | Tham số bắt buộc |
| :--- | :--- | :--- |
| `lookup_bus_route` | Tra cứu tuyến trong cơ sở dữ liệu mô phỏng | `route_code` |
| `register_monthly_pass` | Tạo đăng ký vé tháng mô phỏng | `customer_name`, `phone_number`, `route_code`, `start_date` |

MCP Server công bố hai JSON Schema trên và đóng gói kết quả bằng các trường
`jsonrpc: "2.0"`, `server`, `tool`, `result`. Backend chuẩn hóa mã tuyến, kiểm tra
số điện thoại/ngày bắt đầu/mã tuyến và trả trạng thái có cấu trúc thay vì để LLM
tự bịa dữ liệu.

> **Phạm vi dữ liệu:** toàn bộ tuyến, giá vé và đăng ký trong bài là dữ liệu mô
> phỏng cố định để kiểm thử Lab 3, không phải dữ liệu vận hành VinBus thời gian thực.

## 3. Trích xuất Waterfall Trace Log từ API thật

Đoạn rút gọn dưới đây lấy từ TC04 trong `docs/trace_waterfall.json`. File JSON
gốc lưu đầy đủ query, arguments, Observation, độ trễ LLM/MCP, provider và model.

```json
[
  {
    "step": 1,
    "action_type": "TOOL_EXECUTION",
    "thought": "OpenAI chọn công cụ lookup_bus_route.",
    "tool_name": "lookup_bus_route",
    "arguments": {"route_code": "E05"},
    "observation": {"status": "SUCCESS", "route_code": "E05"},
    "latency_ms": 825.21,
    "jsonrpc": "2.0",
    "provider": "OpenAIProvider",
    "model": "gpt-4o-mini",
    "live_api": true,
    "test_case_id": "TC04"
  },
  {
    "step": 2,
    "action_type": "TOOL_EXECUTION",
    "thought": "OpenAI chọn công cụ register_monthly_pass.",
    "tool_name": "register_monthly_pass",
    "observation": {
      "status": "SUCCESS",
      "registration_id": "VP-769C063575",
      "phone_number_masked": "098****321",
      "route_code": "E05"
    },
    "latency_ms": 1362.62,
    "provider": "OpenAIProvider",
    "model": "gpt-4o-mini",
    "live_api": true,
    "test_case_id": "TC04"
  },
  {
    "step": 3,
    "action_type": "FINAL_ANSWER",
    "thought": "OpenAI đã đủ dữ liệu để trả lời trực tiếp.",
    "latency_ms": 1434.62,
    "provider": "OpenAIProvider",
    "model": "gpt-4o-mini",
    "live_api": true,
    "test_case_id": "TC04"
  }
]
```

## 4. Tổng kết nghiệm thu

- [x] Đã cấu hình và xác nhận Agent chạy trên OpenAI API thật.
- [x] Đã hoàn thành 5 câu hỏi cá nhân hóa theo chủ đề VinBus, không còn `TODO`.
- [x] **5/5 test cases PASS** theo chuỗi tool mong đợi và đều có `FINAL_ANSWER`.
- [x] **5 lượt gọi tool qua MCP**: `lookup_bus_route` 3 lượt, `register_monthly_pass` 2 lượt.
- [x] Trace có **10 events**: 5 `TOOL_EXECUTION` và 5 `FINAL_ANSWER`.
- [x] Tổng độ trễ ghi nhận trong lần chạy nghiệm thu: **16,089.37 ms**.
- [x] TC05 xử lý `NOT_FOUND` đúng và không bịa lộ trình E99.
- [x] Câu trả lời đăng ký chỉ hiển thị số điện thoại đã che.
- [ ] Commit và Push lên GitHub cá nhân (thực hiện sau khi rà soát bài nộp).

Lệnh nghiệm thu:

```powershell
.\.venv\Scripts\python.exe src\app.py --all
```

Kết quả cuối: `5/5 test cases PASS`, tiến trình thoát với mã `0`.
