import requests
import json
import time

url = "http://localhost:8000/api/v1/ppt/pipeline"
headers = {"Content-Type": "application/json", "Authorization": "Bearer test-token"}
data = {
    "topic": "解码霍尔木兹海峡危机：理解其对国际关系的影响",
    "total_pages": 12,
    "audience": "大学生",
    "purpose": "课堂展示",
    "style_preference": "学术风格",
    "with_export": True,
    "quality_profile": "training_deck",
    "execution_profile": "dev_strict",
    "force_ppt_master": True,
}

print("Calling API...")
start = time.time()
response = requests.post(url, headers=headers, json=data, timeout=600)
elapsed = time.time() - start

print(f"Status: {response.status_code}")
print(f"Time: {elapsed:.1f}s")

result = response.json()
with open("agent/pipeline_response.json", "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)

if result.get("success"):
    print("Success!")
    data_obj = result.get("data", {})
    export_result = data_obj.get("export_result")
    if export_result:
        output_file = export_result.get("output_file")
        print(f"Output: {output_file}")
else:
    error_msg = result.get("error", "Unknown error")
    print(f"Error: {error_msg}")
