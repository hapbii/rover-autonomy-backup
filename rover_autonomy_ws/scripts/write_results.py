"""Generate the final report from actual saved test outputs, never guessed metrics."""

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def main():
    tests = ET.parse(ROOT / "artifacts/test_report.xml").getroot()
    suites = [tests] if tests.tag == "testsuite" else list(tests)
    count = sum(int(item.attrib.get("tests", 0)) for item in suites)
    failures = sum(int(item.attrib.get("failures", 0)) + int(item.attrib.get("errors", 0)) for item in suites)
    demo = load("artifacts/demo/report.json")
    memory = load("artifacts/memory_report.json")
    lifecycle = load("artifacts/memory_lifecycle_report.json")
    signs = load("artifacts/sign_synthetic_report.json")
    environment = load("artifacts/environment_report.json")
    firmware = (ROOT / "artifacts/firmware/build_report.txt").read_text(encoding="utf-8")
    flash = re.search(r"Sketch uses (\d+) bytes", firmware)
    ram = re.search(r"Global variables use (\d+) bytes", firmware)
    passed_demos = sum(bool(item["passed"]) for item in demo["results"])
    growth = memory["growth"]
    report = f"""# 개발 결과 — 2026-11-12

이 문서는 Windows 로컬 개발·측정 기록입니다. 이후 Pi 배포·ROS 통합 시험과 현재 장비 상태는 [DEPLOYMENT_REPORT.md](DEPLOYMENT_REPORT.md)를 확인합니다.

## 완료한 로컬 개발

- 카메라 라인 추종, 빨강 정지/초록 재출발, 좌/우 화살표 동작, 전면 초음파 스캔 기반 우회, 손 위치/거리 추종 코드.
- ROS 2 Jazzy 노드/런치/서비스/설정 파일, 좌우 독립 RPM 명령과 Arduino RA1 통신.
- Uno 엔코더 4개 x1 계수, 좌우 평균 속도 PID, 각 엔코더 정지/역방향 감시, 통신 타임아웃.
- 배선 프로필, 실물 복귀 작업 목록, 로컬 실행/향후 Pi 이전 절차와 전송 묶음 준비.
- 최신 핀 구성: 사용자 요청대로 양쪽 STBY=D10 유지, 오른쪽 뒤 엔코더 A/B=A2/A5, D13 미사용. 기존 D13 제안은 폐기.

## 검증 결과

| 항목 | 실제 결과 |
|---|---|
| Python 자동 테스트 | {count}개, 실패/오류 {failures}개 |
| 로컬 통합 데모 | {passed_demos}/{len(demo["results"])}개 시나리오 통과 |
| 표지판 도형 기능 시험 | 합성 {signs["passed_cases"]}/{signs["cases"]}조건 통과, 실제 사진 0장 |
| 메모리 시험 | 워밍업 {memory["warmup_frames"]:,}회 후 {memory["frames_after_warmup"]:,}회 반복 |
| 손 모델 실제 forward | {memory["real_palm_inferences"]}회 (공개 모델/참조 영상, 근접 여백 재검출 포함) |
| Python 유지 메모리 변화 | {growth["traced"] / 1048576:+.3f} MiB |
| 프로세스 RSS 변화 | {growth["rss"] / 1048576:+.3f} MiB |
| 핸들 변화 | {growth["handles"]:+d} |
| 메모리 판정 | {"지정한 반복 조건에서 지속 증가 징후 없음" if memory["passed"] else "기준 초과 — 추가 분석 필요"} |
| 모델·파일 디코더 재시작 시험 | 워밍업 {lifecycle["warmup_cycles"]}회 후 {lifecycle["measured_cycles"]}회, {"통과" if lifecycle["passed"] else "실패"} |
| 재시작 시 Python / RSS 변화 | {lifecycle["growth"]["traced"] / 1048576:+.3f} / {lifecycle["growth"]["rss"] / 1048576:+.3f} MiB |
| 재시작 시 핸들 / 스레드 변화 | {lifecycle["growth"]["handles"]:+d} / {lifecycle["growth"]["threads"]:+d} |
| Uno 프로그램 크기 | {flash.group(1) if flash else "보고서 확인"} / 32,256 bytes |
| Uno 정적 RAM | {ram.group(1) if ram else "보고서 확인"} / 2,048 bytes |
| 로컬 환경 | Python {environment["python"]}, OpenCV {environment["opencv"]}, NumPy {environment["numpy"]}, Windows |

데모는 실제 인식/판단 코드를 실행하지만 차체·초음파는 시뮬레이션입니다. 표지판 입력은 생성한 도형이고 손 입력은 OpenCV Zoo의 공개 참조 영상입니다. 실제 카메라 촬영이나 실차 시험으로 표현하지 않습니다.

## 표지판 자료 정정

사용자는 이번 프로젝트용 표지판 사진/라벨을 제공하지 않았습니다. 초기에 형제 폴더 `yolo_dataset`을 사용자 제공 자료로 잘못 판단한 점을 정정합니다. 그 자료의 출처/적용 가능성은 확인되지 않았고, 파생 모델과 이전 평가 수치는 `experiments/unverified_workspace_dataset`에 보관했습니다. 원본은 변경하지 않았습니다.

기본 실행/배포는 그 자료와 모델을 사용하지 않습니다. 합성 도형 기능 시험만 수행했으며 **실제 표지판 인식률은 미검증**입니다. 데이터가 준비되면 별도의 실제 영상 평가와 필요 시 명시적 학습이 필요합니다.

## 리팩터링 및 수정한 문제

1. 인식·판단·직렬 통신·ROS 어댑터를 분리하고 관측값을 작은 불변 객체로 유지.
2. 최신 프레임 1개, 고정 길이 표지판 이력, 제한된 시리얼 버퍼 및 검출 수로 변경/확인.
3. 모델 매 프레임 재로딩 방지, OpenCV 스레드 수 제한.
4. 카메라 Request의 예외 경로 release, 종료/생성 실패 시 자원 해제, 시리얼 close 보강.
5. 한글 경로에서 ONNX 로딩 실패를 파일 바이트 로딩으로 수정. raw 영상의 행 패딩/RGB 처리 추가.
6. 영상 노드 재시작 시 sequence 초기화 처리와 현재 모드 상태 재전달.
7. ARM 응답 도중 disarm되는 경합, 예기치 않은 보드 재부팅, 중복 텔레메트리로 타임아웃이 연장되는 문제를 방어.
8. 장애물을 완전히 지나기 전에 라인으로 되돌아가던 우회 거리를 감지 거리 기준으로 수정.
9. 가까운 손을 놓치는 경우 1회 여백 재검출을 추가하고, 좌표/면적을 원본 기준으로 복원해 정지 판단.
10. 출처 미확인 표지판 학습 모델의 기본 사용을 제거하고 자료 출처/시험 종류를 명확히 기록.
11. 재점검에서 OpenCV 카메라 설정 실패 시 release 누락, 종료 오류 시 참조 유지/중복 close 경로 수정.
12. 파이프라인 초기화 실패와 데모 참조 이미지/영상 기록 실패에도 모델·디코더·임시 파일을 정리하도록 ExitStack 적용.
13. 시리얼 종료 시 전송 객체·수신 버퍼·최근 텔레메트리를 비우고, ROS 노드의 장치 종료 오류에도 상위 노드 정리를 실행하도록 보강.
14. 파일 영상 디코더는 FFmpeg open 시 디코더 스레드를 1개로 제한. 실제 장치 인덱스의 기존 카메라 경로는 유지.

이번 재점검의 상세 변경과 메모리 결과는 [REFRACTOR_REPORT.md](REFRACTOR_REPORT.md)에 있습니다.

메모리 시험은 이 PC에서 실제 OpenCV 네트워크와 순수 로직·가상 시리얼을 반복한 결과입니다. Pi의 libcamera/ROS DDS/실물 USB 환경 전체에 누수가 없다는 보장은 아닙니다.

## 로컬 측정 당시 범위와 실물 미검증 항목

- 로컬 메모리 측정 당시에는 Pi/ROS 실행을 포함하지 않았습니다. 이후 SSH 배포와 ROS 통합 시험 결과는 DEPLOYMENT_REPORT.md에 별도로 기록했습니다.
- 실제 Pi 카메라/초음파/엔코더 배선 및 신호, 새 펌웨어 업로드, PID/전진 방향 보정.
- 실제 표지판/라인/손 영상의 정확도, 프레임 속도, 센서 지연과 실차 주행.
- cm 단위 손 거리의 실측 보정. 기본은 상대적인 손바닥 크기 제어.

하드웨어 출력은 기본 비활성이고 미측정 치수/CPR은 0으로 두어 실물 출력을 거부합니다. 실물 복귀 후 작업은 [WIRING.md](WIRING.md), 명령어/코드 위치는 [README.md](README.md)에 있습니다.

## 증거 파일

- `artifacts/test_report.xml`
- `artifacts/demo/report.json`, `artifacts/demo/*.mp4`
- `artifacts/sign_synthetic_report.json`
- `artifacts/memory_report.json`
- `artifacts/memory_lifecycle_report.json`
- `artifacts/firmware/build_report.txt`
- `artifacts/environment_report.json`
"""
    (ROOT / "DEVELOPMENT_REPORT.md").write_text(report, encoding="utf-8")
    refactor = f"""# 전체 코드 재검토·리팩터링 및 메모리 재시험 — 2026-11-12

## 변경 내용과 근거

기존 정상 경로 테스트 77개는 통과한 상태에서 예외·종료 경로를 추가로 검토했습니다. 먼저 작성한 자원 관련 회귀 시험 9건이 이전 코드에서 실패하는 것을 확인한 뒤 수정했고, 초기화/정리 예외와 디코더 설정 시험을 추가했습니다. 최종 자동 테스트는 {count}개, 실패/오류 {failures}개입니다.

- `hardware/camera.py`: 카메라를 연 뒤 설정이 실패해도 release. close 도중 오류가 나도 소유 참조를 해제하고 중복 release 방지. Pi 카메라는 stop 실패 시에도 close 시도 및 참조 해제.
- `vision/pipeline.py`: 생성 실패 시 전달받은 손 모델 정리, 종료된 파이프라인 재사용 거부, 모델 close 실패 시에도 소유 참조 해제.
- `hardware/protocol.py`: 시리얼 종료 후 포트 객체·수신 버퍼·텔레메트리 참조 제거 및 닫힘 상태 명시.
- `ros/*_node.py`: 외부 자원 close가 실패해도 상위 Node 정리 실행. 베이스 재연결에서 종료 예외 처리, 잘못된 JSON 베이스 상태 형식 처리 보강.
- `scripts/run_demo.py`: 모델 초기화 이후 참조 이미지/영상 기록이 실패해도 자원 정리. 실패한 MP4 임시 파일 제거.
- `scripts/memory_soak.py`: ExitStack으로 모든 정리 실행, 샘플 이력 상한, 손 추론 빈도 증가, 유지 메모리 추세 추가 확인.
- `scripts/memory_lifecycle.py`: 실제 ONNX 로드/추론/종료와 로컬 MP4 디코더 열기/읽기/종료를 반복. 시리얼은 가상 장치만 사용.
- 파일 입력 디코더는 `CAP_PROP_N_THREADS=1`을 open 시 지정. OpenCV의 일반 연산 스레드 제한과 별도로 코덱 스레드 설정이 필요합니다. [OpenCV 공식 설정 문서](https://docs.opencv.org/4.10.0/d4/d15/group__videoio__flags__base.html)

## 최종 측정

| 항목 | 연속 처리 | 모델·파일 디코더 재시작 |
|---|---|---|
| 워밍업 | {memory["warmup_frames"]:,}프레임 | {lifecycle["warmup_cycles"]}회 |
| 측정 반복 | {memory["frames_after_warmup"]:,}프레임 | {lifecycle["measured_cycles"]}회 |
| 실제 손 모델 forward, 워밍업 포함 | {memory["real_palm_inferences"]:,}회 | {lifecycle["real_palm_inferences"]:,}회 |
| Python 유지 메모리 변화 | {growth["traced"] / 1048576:+.3f} MiB | {lifecycle["growth"]["traced"] / 1048576:+.3f} MiB |
| RSS 변화 | {growth["rss"] / 1048576:+.3f} MiB | {lifecycle["growth"]["rss"] / 1048576:+.3f} MiB |
| 핸들 변화 | {growth["handles"]:+d} | {lifecycle["growth"]["handles"]:+d} |
| 스레드 변화 | {growth["threads"]:+d} | {lifecycle["growth"]["threads"]:+d} |
| 결과 | {"통과" if memory["passed"] else "실패"} | {"통과" if lifecycle["passed"] else "실패"} |

현재 측정한 파일 디코더: {lifecycle["decoder_backend"]}, 디코더 스레드 {lifecycle["decoder_threads"]}개.

이 메모리 장기 측정은 STBY를 D10으로 복원하기 직전의 리팩터링 결과입니다. 이후 STBY D10 / 오른쪽 뒤 엔코더 A2 핀 배정·식별 문자열 및 Pi ROS의 중복 종료 신호 보호를 수정하고 각 변경을 재검증했습니다. 이 변경 후 장기 메모리 시험을 다시 실행한 결과로 표현하지 않습니다. Pi 검증은 [DEPLOYMENT_REPORT.md](DEPLOYMENT_REPORT.md)에 있습니다.

초기 자동 스레드 디코더 시험은 스레드 +2로 설정한 기준을 넘었습니다. 디코더를 1개 스레드로 제한한 짧은 워밍업 시험도 스레드 +2로 기준을 넘었습니다. 별도 400회 관찰에서는 전체 스레드 수가 19 → 21 → 18로 변해 계속 누적되지는 않았습니다. 추가 스레드의 정확한 기원은 확정하지 않았고, 지속 누수로 단정하지 않았습니다. 초기화 구간과 장기 누적을 분리하기 위해 워밍업/측정 횟수를 위 표처럼 늘려 재시험했습니다. 초기 실패 결과와 추가 관찰은 `artifacts/refactor_debug/`에 보관하며, 수치 판정 기준은 완화하지 않았습니다.

지정 조건에서 지속적인 메모리 누적 징후를 찾지 못했다는 의미입니다. Pi의 ROS DDS/libcamera/실제 USB 장치까지 누수가 없다는 보장은 아닙니다. 이 메모리 측정 당시 ROS 종료 경로는 정적 검사만 했고, 이후 실제 Pi에서 종료 신호 문제를 추가 수정·재시험했습니다. 상세 내용은 DEPLOYMENT_REPORT.md에 있습니다.

## 기타 검증과 산출물

- Python 자동 테스트 {count}개, 실패/오류 {failures}개.
- 로컬 영상 처리·판단 + 가상 차체 데모 {passed_demos}/{len(demo["results"])} 통과.
- 표지판 합성 도형 {signs["passed_cases"]}/{signs["cases"]} 통과. 실제 표지판 사진 성능은 여전히 미검증.
- Uno 재컴파일: 프로그램 {flash.group(1) if flash else "보고서 확인"} bytes, 정적 RAM {ram.group(1) if ram else "보고서 확인"} bytes. 동적 String/new/malloc 없음.
- 수정 전 소스 백업: `artifacts/refactor_before_*.zip`. Raspberry Pi의 `robot_ws` 전체 백업과는 별개이며, 원격 정리/업로드는 아직 실행하지 않았습니다.
- 최종 수치: `artifacts/memory_report.json`, `artifacts/memory_lifecycle_report.json`, `artifacts/test_report.xml`.
"""
    (ROOT / "REFRACTOR_REPORT.md").write_text(refactor, encoding="utf-8")
    print(
        f"Report generated: tests={count}, failures={failures}, demos={passed_demos}, memory_pass={memory['passed']}"
    )
    if (
        failures
        or not demo["passed"]
        or not memory["passed"]
        or not lifecycle["passed"]
        or not signs["passed"]
    ):
        raise SystemExit("One or more verification stages failed")


if __name__ == "__main__":
    main()
