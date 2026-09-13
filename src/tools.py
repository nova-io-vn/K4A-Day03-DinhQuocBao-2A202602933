"""
Tool schemas và execution backend cho Trợ lý Dịch vụ Khách hàng VinBus.

Dữ liệu trong module này là dữ liệu mô phỏng phục vụ Lab 3. Không sử dụng các
kết quả này như thông tin vận hành VinBus ngoài đời thực.
"""

import hashlib
import json
import re
from datetime import date, datetime
from typing import Any, Dict


TOOLS_SCHEMA = [
    {
        "name": "lookup_bus_route",
        "description": (
            "Tra cứu lộ trình, điểm đầu/cuối, giờ hoạt động, tần suất và giá vé "
            "mô phỏng của một tuyến xe buýt điện VinBus theo mã tuyến."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "route_code": {
                    "type": "string",
                    "description": "Mã tuyến cần tra cứu, ví dụ E01, E03 hoặc E05.",
                }
            },
            "required": ["route_code"],
            "additionalProperties": False,
        },
    },
    {
        "name": "register_monthly_pass",
        "description": (
            "Đăng ký vé tháng mô phỏng cho khách hàng trên một tuyến VinBus. "
            "Chỉ gọi khi đã có đủ họ tên, số điện thoại, mã tuyến và ngày bắt đầu."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {
                    "type": "string",
                    "description": "Họ và tên khách hàng đăng ký vé tháng.",
                },
                "phone_number": {
                    "type": "string",
                    "description": "Số điện thoại Việt Nam gồm 10 chữ số, bắt đầu bằng 0.",
                    "pattern": "^0[0-9]{9}$",
                },
                "route_code": {
                    "type": "string",
                    "description": "Mã tuyến VinBus muốn đăng ký, ví dụ E01.",
                },
                "start_date": {
                    "type": "string",
                    "description": "Ngày bắt đầu hiệu lực theo định dạng YYYY-MM-DD.",
                    "format": "date",
                },
            },
            "required": ["customer_name", "phone_number", "route_code", "start_date"],
            "additionalProperties": False,
        },
    },
]


# Dữ liệu giả lập cố định để bài lab có thể kiểm thử lặp lại và không phụ thuộc
# vào một API vận tải bên ngoài.
MOCK_ROUTE_DATABASE = {
    "E01": {
        "route_name": "Bến xe Mỹ Đình - KĐT Ocean Park",
        "origin": "Bến xe Mỹ Đình",
        "destination": "KĐT Ocean Park",
        "operating_hours": "05:00-21:00",
        "frequency_minutes": "15-20",
        "sample_stops": ["Cầu Giấy", "Nhà hát Lớn", "Long Biên"],
        "single_fare_vnd": 9000,
    },
    "E03": {
        "route_name": "Mỹ Đình - KĐT Ocean Park",
        "origin": "Mỹ Đình",
        "destination": "KĐT Ocean Park",
        "operating_hours": "05:00-21:00",
        "frequency_minutes": "15-20",
        "sample_stops": ["Trần Duy Hưng", "Times City", "Cổ Linh"],
        "single_fare_vnd": 9000,
    },
    "E05": {
        "route_name": "Long Biên - Smart City",
        "origin": "Long Biên",
        "destination": "Smart City",
        "operating_hours": "05:00-21:00",
        "frequency_minutes": "15-20",
        "sample_stops": ["Hồ Hoàn Kiếm", "Kim Mã", "Mễ Trì"],
        "single_fare_vnd": 9000,
    },
}


def execute_lookup_bus_route(route_code: str) -> str:
    """Tra cứu một tuyến trong cơ sở dữ liệu mô phỏng."""
    normalized_code = str(route_code).strip().upper()
    route = MOCK_ROUTE_DATABASE.get(normalized_code)
    if route is None:
        return json.dumps(
            {
                "status": "NOT_FOUND",
                "route_code": normalized_code,
                "message": f"Không tìm thấy tuyến có mã '{normalized_code}' trong dữ liệu mô phỏng.",
                "available_route_codes": sorted(MOCK_ROUTE_DATABASE),
                "data_source": "Dữ liệu mô phỏng phục vụ Lab 3",
            },
            ensure_ascii=False,
        )

    return json.dumps(
        {
            "status": "SUCCESS",
            "route_code": normalized_code,
            "data": route,
            "data_source": "Dữ liệu mô phỏng phục vụ Lab 3",
        },
        ensure_ascii=False,
    )


def execute_register_monthly_pass(
    customer_name: str,
    phone_number: str,
    route_code: str,
    start_date: str,
) -> str:
    """Kiểm tra đầu vào và tạo đăng ký vé tháng mô phỏng."""
    normalized_name = str(customer_name).strip()
    normalized_phone = re.sub(r"\s+", "", str(phone_number))
    normalized_route = str(route_code).strip().upper()

    validation_errors = []
    if len(normalized_name) < 2:
        validation_errors.append("customer_name phải có ít nhất 2 ký tự")
    if not re.fullmatch(r"0\d{9}", normalized_phone):
        validation_errors.append("phone_number phải gồm 10 chữ số và bắt đầu bằng 0")
    if normalized_route not in MOCK_ROUTE_DATABASE:
        validation_errors.append(f"route_code '{normalized_route}' không tồn tại trong dữ liệu mô phỏng")

    try:
        parsed_start_date = datetime.strptime(str(start_date), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        parsed_start_date = None
        validation_errors.append("start_date phải đúng định dạng YYYY-MM-DD")

    if parsed_start_date and parsed_start_date < date.today():
        validation_errors.append("start_date không được là ngày trong quá khứ")

    if validation_errors:
        return json.dumps(
            {
                "status": "VALIDATION_ERROR",
                "message": "Không thể đăng ký vé tháng vì dữ liệu đầu vào chưa hợp lệ.",
                "errors": validation_errors,
            },
            ensure_ascii=False,
        )

    booking_seed = f"{normalized_name}|{normalized_phone}|{normalized_route}|{start_date}"
    registration_id = "VP-" + hashlib.sha256(booking_seed.encode("utf-8")).hexdigest()[:10].upper()
    return json.dumps(
        {
            "status": "SUCCESS",
            "registration_id": registration_id,
            "customer_name": normalized_name,
            "phone_number_masked": f"{normalized_phone[:3]}****{normalized_phone[-3:]}",
            "route_code": normalized_route,
            "start_date": str(start_date),
            "message": (
                f"Đã tạo đăng ký vé tháng mô phỏng {registration_id} cho {normalized_name}, "
                f"tuyến {normalized_route}, hiệu lực từ {start_date}."
            ),
            "data_source": "Giao dịch mô phỏng phục vụ Lab 3",
        },
        ensure_ascii=False,
    )


TOOL_ROUTER = {
    "lookup_bus_route": execute_lookup_bus_route,
    "register_monthly_pass": execute_register_monthly_pass,
}


def dispatch_tool_call(tool_name: str, arguments: Dict[str, Any]) -> str:
    """Định tuyến và thực thi tool, luôn trả về một chuỗi JSON hợp lệ."""
    function = TOOL_ROUTER.get(tool_name)
    if function is None:
        return json.dumps(
            {"status": "UNKNOWN_TOOL", "error": f"Tool '{tool_name}' không tồn tại."},
            ensure_ascii=False,
        )
    if not isinstance(arguments, dict):
        return json.dumps(
            {"status": "INVALID_ARGUMENTS", "error": "arguments phải là một JSON object."},
            ensure_ascii=False,
        )

    try:
        return function(**arguments)
    except TypeError as exc:
        return json.dumps(
            {"status": "INVALID_ARGUMENTS", "error": str(exc)},
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps(
            {"status": "EXECUTION_ERROR", "error": str(exc)},
            ensure_ascii=False,
        )
