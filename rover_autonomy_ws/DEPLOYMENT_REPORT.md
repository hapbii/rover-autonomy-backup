# Pi 배포·점검 결과 — 2026-11-12T10:09:18.324457+00:00

## 완료

- SSH 접속: `takyeji@192.168.50.34`. 사용자 요청으로 재부팅 후 재접속 확인.
- 실제 작업 폴더: `/home/takyeji/robot_ws`. 로컬 폴더 이름 rover_autonomy_ws와 구분.
- 전체 백업: `/home/takyeji/robot_ws_backup_20261112_094404`. 숨김 파일/펌웨어/기존 보드 백업 포함, 파일 432개 SHA-256 및 디렉터리·링크 검증. 정리 후 백업 내용을 다시 확인.
- 이전 build/install/log·대체된 패키지·참고 펌웨어 정리. `.git`과 `firmware/backups` 유지. 재빌드에 필요한 새 build/install/log는 다시 생성됨.
- Python3.12 venv/의존성 설치 및 ROS 2 Jazzy colcon 빌드 완료.
- Pi 자동 테스트 90개, 실패 0·오류 0·건너뜀 0개.
- 실제 ROS 가상 주행 및 참조 이미지 손 추종 시험 통과. 별도 도메인190, 가상 거리, 하드웨어 출력 비활성. 실제 카메라/초음파/차량 시험이 아님.
- ROS 종료 시 중복 SIGINT로 자원 정리가 중단되는 문제를 재현·수정. 재시험에서 비상정지와 정상 종료, traceback 없음 확인.
- 새 RA1 펌웨어는 STBY=D10, 오른쪽 뒤 엔코더 A/B=A2/A5. 업로드와 실제 모터 출력은 실행하지 않음.

## 삭제한 기존 경로

전체 백업을 검증한 뒤 다음 경로를 정리했습니다. 기존 encoder_motor 테스트는 활성 폴더에서 제거했으며 백업에 보존했습니다.

- `build`
- `install`
- `log`
- `src/robot_base`
- `src/robot_mission`
- `src/robot_bringup`
- `src/encoder_motor`
- `firmware/two_motor_test`
- `firmware/two_motor_test_stby13`
- `firmware/three_ir_four_encoder`
- `firmware/robot_arduino`
- `scripts/setup_pi.sh`

임시 전송 폴더와 새 시험에서 생성한 캐시도 제거했습니다. 소스/설정 파일은 새 rover_autonomy 패키지로 교체했습니다.

## 남은 작업

1. **Uno USB 인식 복구.** 재부팅 후에도 lsusb에 Uno가 없고 ttyACM/ttyUSB 장치가 없습니다. ROS 코드/시리얼 권한보다 앞선 USB 열거 단계의 문제로 보이며 정확한 원인은 아직 미확정입니다. 모터 전원을 끄고 외부 배선을 분리한 뒤 USB만, 다른 데이터 케이블/포트/PC로 비교합니다. ON LED만으로 데이터 연결을 확인할 수 없습니다. [Arduino 공식 점검](https://support.arduino.cc/hc/en-us/articles/4412955149586-If-your-board-is-not-detected-by-Arduino-IDE)
2. **실제 카메라 스택 복구.** OV5647 모델은 인식하지만 영상 획득은 실패했습니다. ROS libcamera0.7.2는 ControlInfoMap 직렬화 오류, 시스템 libcamera0.2.0의 직접 cam 캡처도 prepareIsp 버퍼 assertion으로 실패합니다. 따라서 Python 영상 처리보다 아래 단계의 오류도 존재합니다. Picamera2 미설치이며 현재 실제 카메라 실행 성공을 주장하지 않습니다. 시험용 V4L2 호환 패키지는 실패 후 제거했습니다. OS 업그레이드나 시스템 카메라 스택 전체 교체는 실행하지 않았습니다.
3. 엔코더/초음파 모델·핀·전압·배선 확인, 바퀴 치수/CPR/방향 부호 실측.
4. RA1 새 펌웨어 업로드 후 바퀴를 띄워 저출력 정방향/역방향·좌우 속도 제어 확인.
5. 실제 라인/표지판/손 영상 평가 및 실차 튜닝. 표지판 실사진 정확도는 여전히 미검증.

## 현재 실행 가능한 명령

```bash
source ~/robot_ws/env.sh
cd ~/robot_ws
ros2 launch rover_autonomy simulation.launch.py
```

자동 ROS 통합 시험은 실제 모터/카메라 대신 가상 입력을 씁니다:

```bash
python scripts/ros_smoke.py --scenario simulation
python scripts/ros_smoke.py --scenario image
```

현재 실제 모터 출력 설정은 false, calibrated도 false입니다. 실제 카메라 구동은 위 스택 문제 복구 후 진행합니다.

## 증거

- `artifacts/pi_deployment/pi_deployment_report.json`
- `artifacts/pi_deployment/backup_verification.json`
- `artifacts/pi_deployment/deployment_cleanup.json`
- `artifacts/pi_deployment/pi_test_report.xml`
- `artifacts/pi_deployment/pi_ros_simulation_report.json`, `pi_ros_image_report.json`
- Pi 원본 로그: `~/robot_ws/artifacts/pi_setup.log`, `pi_ros_*.log`, `cam_capture_final.log`.
