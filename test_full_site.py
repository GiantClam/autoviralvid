"""
Full website test
"""

import requests
import json
import time
from datetime import datetime

BASE_URL = "http://localhost:3001"
AGENT_URL = "http://localhost:8123"


def test(name, condition, details=""):
    status = "[PASS]" if condition else "[FAIL]"
    print(f"{status} - {name}")
    if details:
        print(f"      {details}")
    return condition


def print_header(title):
    print(f"\n{'=' * 60}")
    print(f"{title}")
    print(f"{'=' * 60}")


def main():
    results = []
    start_time = time.time()

    print(f"\n=== Full Website Test ===")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. Basic Service Tests
    print_header("1. Basic Service Tests")

    try:
        r = requests.get(BASE_URL, timeout=10)
        results.append(
            test("Next.js Homepage", r.status_code == 200, f"Status: {r.status_code}")
        )
    except Exception as e:
        results.append(test("Next.js Homepage", False, str(e)))

    try:
        r = requests.get(f"{AGENT_URL}/healthz", timeout=5)
        results.append(
            test("Agent /healthz", r.status_code == 200, f"Status: {r.status_code}")
        )
    except Exception as e:
        results.append(test("Agent /healthz", False, str(e)))

    try:
        r = requests.get(f"{AGENT_URL}/render/health", timeout=5)
        data = r.json()
        results.append(
            test(
                "Render Service Health",
                r.status_code == 200,
                f"FFmpeg: {data.get('ffmpeg_available')}",
            )
        )
    except Exception as e:
        results.append(test("Render Service Health", False, str(e)))

    # 2. Render API Tests
    print_header("2. Render API Tests")

    try:
        r = requests.post(
            f"{BASE_URL}/api/render/jobs",
            json={
                "project": {
                    "name": "Test",
                    "width": 1920,
                    "height": 1080,
                    "duration": 5,
                    "fps": 30,
                    "tracks": [],
                }
            },
            timeout=10,
        )
        results.append(
            test(
                "Render API - Empty Project",
                r.status_code == 200,
                f"Mode: {r.json().get('mode')}",
            )
        )
    except Exception as e:
        results.append(test("Render API - Empty Project", False, str(e)))

    try:
        r = requests.post(
            f"{BASE_URL}/api/render/jobs",
            json={
                "project": {
                    "name": "Test Full Project",
                    "width": 1920,
                    "height": 1080,
                    "duration": 10,
                    "fps": 30,
                    "backgroundColor": "#4ECDC4",
                    "tracks": [
                        {
                            "id": 2,
                            "type": "overlay",
                            "name": "Text",
                            "items": [
                                {
                                    "id": "text-1",
                                    "type": "text",
                                    "content": "Test Title",
                                    "startTime": 0,
                                    "duration": 10,
                                    "trackId": 2,
                                    "name": "Title",
                                }
                            ],
                        }
                    ],
                }
            },
            timeout=10,
        )
        data = r.json()
        results.append(
            test(
                "Render API - Full Project",
                r.status_code == 200,
                f"Layers: {data.get('summary', {}).get('layerCount')}",
            )
        )
    except Exception as e:
        results.append(test("Render API - Full Project", False, str(e)))

    # 3. 30-second Video Render Test
    print_header("3. 30-second Video Render Test")

    try:
        r = requests.post(
            f"{BASE_URL}/api/render/jobs",
            json={
                "project": {
                    "name": "Test 30s",
                    "width": 1920,
                    "height": 1080,
                    "duration": 30,
                    "fps": 30,
                    "backgroundColor": "#1a1a2e",
                    "tracks": [
                        {
                            "id": 2,
                            "type": "overlay",
                            "name": "Text",
                            "items": [
                                {
                                    "id": "t1",
                                    "type": "text",
                                    "content": "Welcome",
                                    "startTime": 0,
                                    "duration": 10,
                                    "trackId": 2,
                                    "name": "T1",
                                },
                                {
                                    "id": "t2",
                                    "type": "text",
                                    "content": "Key Points",
                                    "startTime": 10,
                                    "duration": 10,
                                    "trackId": 2,
                                    "name": "T2",
                                },
                                {
                                    "id": "t3",
                                    "type": "text",
                                    "content": "Thank You",
                                    "startTime": 20,
                                    "duration": 10,
                                    "trackId": 2,
                                    "name": "T3",
                                },
                            ],
                        }
                    ],
                    "runId": f"test-{int(time.time())}",
                }
            },
            timeout=10,
        )

        data = r.json()
        job_id = data.get("job_id")

        if job_id and data.get("mode") == "remote":
            print(f"      Job ID: {job_id}")
            start = time.time()
            while True:
                status_r = requests.get(f"{AGENT_URL}/render/jobs/{job_id}", timeout=5)
                status_data = status_r.json()
                elapsed = time.time() - start

                if status_data.get("status") == "completed":
                    render_time = elapsed
                    results.append(
                        test("30s Video Render", True, f"Time: {render_time:.2f}s")
                    )
                    break
                elif status_data.get("status") == "failed":
                    results.append(
                        test(
                            "30s Video Render",
                            False,
                            f"Error: {status_data.get('error')}",
                        )
                    )
                    break

                if elapsed > 120:
                    results.append(test("30s Video Render", False, "Timeout"))
                    break
                time.sleep(1)
        else:
            results.append(test("30s Video Render", False, f"No valid job ID"))
    except Exception as e:
        results.append(test("30s Video Render", False, str(e)))

    # 4. 1-minute Video Render Test
    print_header("4. 1-minute Video Render Test")

    try:
        r = requests.post(
            f"{BASE_URL}/api/render/jobs",
            json={
                "project": {
                    "name": "Test 1min",
                    "width": 1920,
                    "height": 1080,
                    "duration": 60,
                    "fps": 30,
                    "backgroundColor": "#4ECDC4",
                    "tracks": [
                        {
                            "id": 2,
                            "type": "overlay",
                            "name": "Text",
                            "items": [
                                {
                                    "id": "t1",
                                    "type": "text",
                                    "content": "Chapter 1",
                                    "startTime": 0,
                                    "duration": 15,
                                    "trackId": 2,
                                    "name": "T1",
                                },
                                {
                                    "id": "t2",
                                    "type": "text",
                                    "content": "Chapter 2",
                                    "startTime": 15,
                                    "duration": 15,
                                    "trackId": 2,
                                    "name": "T2",
                                },
                                {
                                    "id": "t3",
                                    "type": "text",
                                    "content": "Chapter 3",
                                    "startTime": 30,
                                    "duration": 15,
                                    "trackId": 2,
                                    "name": "T3",
                                },
                                {
                                    "id": "t4",
                                    "type": "text",
                                    "content": "Chapter 4",
                                    "startTime": 45,
                                    "duration": 15,
                                    "trackId": 2,
                                    "name": "T4",
                                },
                            ],
                        }
                    ],
                    "runId": f"fulltest-{int(time.time())}",
                }
            },
            timeout=10,
        )

        data = r.json()
        job_id = data.get("job_id")

        if job_id:
            print(f"      Job ID: {job_id}")
            start = time.time()
            while True:
                status_r = requests.get(f"{AGENT_URL}/render/jobs/{job_id}", timeout=5)
                status_data = status_r.json()
                elapsed = time.time() - start

                if status_data.get("status") == "completed":
                    render_time = elapsed
                    realtime_factor = 60 / render_time
                    results.append(
                        test(
                            "1min Video Render",
                            True,
                            f"Time: {render_time:.2f}s, Speed: {realtime_factor:.1f}x",
                        )
                    )
                    break
                elif status_data.get("status") == "failed":
                    results.append(
                        test(
                            "1min Video Render",
                            False,
                            f"Error: {status_data.get('error')}",
                        )
                    )
                    break

                if elapsed > 180:
                    results.append(test("1min Video Render", False, "Timeout"))
                    break
                time.sleep(1)
    except Exception as e:
        results.append(test("1min Video Render", False, str(e)))

    # 5. Other API Tests
    print_header("5. Other API Tests")

    try:
        r = requests.post(
            f"{BASE_URL}/api/upload/presign",
            json={"filename": "test.mp4", "contentType": "video/mp4"},
            timeout=5,
        )
        results.append(
            test(
                "Upload Presign API",
                r.status_code in [200, 401],
                f"Status: {r.status_code}",
            )
        )
    except Exception as e:
        results.append(test("Upload Presign API", False, str(e)))

    try:
        r = requests.get(f"{BASE_URL}/api/quota", timeout=5)
        results.append(
            test("Quota API", r.status_code in [200, 401], f"Status: {r.status_code}")
        )
    except Exception as e:
        results.append(test("Quota API", False, str(e)))

    try:
        r = requests.get(f"{BASE_URL}/favicon.ico", timeout=5)
        results.append(
            test("Favicon", r.status_code == 200, f"Status: {r.status_code}")
        )
    except Exception as e:
        results.append(test("Favicon", False, str(e)))

    # 6. Summary
    print_header("6. Test Summary")

    passed = sum(results)
    total = len(results)
    percentage = (passed / total * 100) if total > 0 else 0
    total_time = time.time() - start_time

    print(f"\nTotal Tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    print(f"Pass Rate: {percentage:.1f}%")
    print(f"Total Time: {total_time:.2f}s")

    if percentage >= 90:
        print("\n[OK] Website is ready for production!")
    elif percentage >= 70:
        print("\n[WARN] Website is usable, some features need fixes")
    else:
        print("\n[ERROR] Website has issues, needs fixes")

    return percentage >= 90


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
