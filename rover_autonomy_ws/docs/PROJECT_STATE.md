# 최신 UART 배포 상태 — 2026-11-13

- SSH 접속·Pi 새 코드 배포·ROS 빌드 완료. 전체 백업 `/home/takyeji/robot_ws_backup_20261113_102324` 일반 파일 1,503개 및 메타데이터 검증.
- 통신은 USB 대신 Pi GPIO14 TX→Uno D0 RX, Uno D1 TX→5V/3.3V 변환→Pi GPIO15 RX. 기본 `/dev/serial0`은 udev 규칙으로 `/dev/ttyAMA0`에 연결. 시리얼 콘솔 해제·disable-bt·I2C/SPI/아날로그 오디오 해제 후 재부팅·재접속 완료. 모터 GPIO14/15 예약 검사 추가.
- 공식 pigpiod v79 별도 빌드·설치. localhost-only 실행. IPv6 localhost 바인딩 때문에 코드 접속을 localhost로 수정. 실제 PWM 0/감시 timeout latch·출력 거부·STBY LOW 확인. 비영 PWM·모터 구동은 실행하지 않음.
- 가상 주행·공개 참조 이미지 손 추종 ROS 통합 시험 통과. 최종 로컬 테스트 150개 및 Ruff 통과. 최종 Pi 재시험도 150개 통과, Ruff 오류 없음.
- 카메라 해결: libcamera 0.2.0 embedded-buffer 초기화 결함을 별도 소스 트리에서 수정. native 3프레임, PiCamera 30프레임, 실제 ROS 20프레임 약12fps와 정상 종료 확인. `source env.sh`가 별도 camera_env.sh를 불러 검증한 라이브러리/Python 경로 적용. 기본 시스템/ROS 라이브러리 보존.
- 지원 소스는 ~/rover_support/libcamera-v0.2.0-fixed 및 kmsxx. Picamera2 0.3.17. 재현 스크립트 scripts/build_camera_stack.py, 선택 의존성 requirements-camera-pi.txt. 이 Pi 지원 폴더가 이전 노트북/GitHub 백업에 들어 있다고 가정하지 말 것.
- Uno는 노트북 COM8에서 인식되며 EM2 BOOT 응답. 사용자 D0/D1 분리·모터 전원 OFF 확인. flash/EEPROM 읽기와 업로드는 부트로더 sync 실패. 보드 새 백업/RA2 업로드 성공으로 보고하지 말 것. 사용자 RESET 1회 후에도 해결 안 됨. 전체 배선 분리는 현재 어렵다는 답변에 따라 추가 리셋·업로드 재시도 중단.
- UART 레벨 변환은 아직 준비 확인 안 됨. Uno TX 5V→Pi RX 직결 금지와 1kΩ/2kΩ 분압 안내. 변환과 새 RA2 전에는 실제 UART/실차 통합을 진행하지 않음. 기본 enabled/calibrated=false.
- 상세: UART_DEPLOYMENT_REPORT.md, WIRING.md. 아래는 이전 시점 기록이며 최신 상태와 구분할 것.

---

# 최신 상태 — 2026-11-13 Pi 모터 제어 전환

- 사용자 확정: 1번 왼쪽, 2번 오른쪽. PWM은 왼쪽 12/18, 오른쪽 13/19 BCM GPIO에 각 입력을 따로 연결해 공유 채널로 제어.
- 최종 방향핀: 왼쪽 AIN1/2=4/3, BIN1/2=27/22, STBY=17. 오른쪽 AIN1/2=5/23, BIN1/2=9/11, STBY=6. 오른쪽 AIN2는 기존 GPIO0 대신23 배정했음을 사용자에게 명시할 것.
- Uno 엔코더는 LF2/4 RF6/7 LRA3/A4 RRA2/A5 유지. 초음파 A0/A1, IR 왼쪽부터 D8~D12. D0/D1 USB 예약.
- 로컬 코드: Pi PWM/PID + RA2 센서 펌웨어·USB 통신·ROS base/bench·IR 토픽·설정·배선 문서 변경. 148 테스트 및 Ruff 통과, 새 Uno RA2 컴파일 성공. 실제 Pi 전송/ROS 빌드/업로드/모터 실행은 아직 하지 않음.
- 기본 enabled/calibrated=false 유지. 새 의존성은 pigpio Python 클라이언트와 별도 로컬 pigpiod. Pi 4 backend만 구현. IR은 디지털 OUT 가정, 실제 규격·극성 확인 필요. IR 자동 라인 전환 없음.
- 이전 RA1/EM2 보드 펌웨어는 IR 핀을 출력으로 설정하므로 센서 연결 전에 RA2 업로드. 이전 sketch 경로는 빌드를 차단하고 rover_sensors 경로를 안내.
- 상세: WIRING.md, README.md, PIN_MIGRATION_REPORT.md. 아래 기록은 이전 배포 당시 상태이며 현재 핀 지시가 아님.

---

# 다음 작업을 위한 상태 기록 — 2026-11-12

## 최신 중단·백업 상태

- 모터 벤치 노드 `rover_autonomy motor_bench_test` 추가. 기존 EM2 시험을 현재 좌우 드라이버 그룹용으로 복원했으며 기본 PWM48/255, 오른쪽/왼쪽/전체 각 0.5초, 최종 STOP. RA1 보정 검사를 우회하지 않음.
- 로컬 및 Pi 최신 자동 테스트 111개 통과. Pi에서 실제 ROS 명령을 실행했으나 `/dev/ttyACM0` 미존재로 포트 열기 실패, 구동 명령 전송 없음.
- 사용자: 바퀴 4개 띄움/전원 차단 가능 확인. 포트를 바꾸면 전원 LED는 켜지지만 USB 장치 미인식. 사용자 재배선을 위해 대기 요청하여 하드웨어 작업 중단.
- 이후 사용자는 노트북 상위 `새 폴더` 삭제에 대비해 현재 프로젝트 관련 모든 파일을 비공개 GitHub 저장소에 백업/커밋하도록 요청. `.venv`·도구·캐시·과거 실험도 이 백업에서는 보존한다.
- Pi는 현재 사용할 수 없어 SSH 시간 초과. 사용자는 노트북부터 백업하라고 명시. Pi에만 있는 전체 `robot_ws`/기존 전체 백업 원본을 GitHub에 보관했다고 보고하면 안 됨.

- 초기에는 Pi가 없어 로컬 개발했으며, 이후 `takyeji@192.168.50.34` SSH 접속 성공. 현재 활성 워크스페이스는 `/home/takyeji/robot_ws`이며 새 코드 배포/ROS 빌드 완료.
- 전체 백업: `/home/takyeji/robot_ws_backup_20261112_094404`, 432개 파일 SHA-256 검증 및 정리 후 재검증 완료. `.git`과 `firmware/backups`는 활성 폴더에도 보존. 이전 4개 패키지/참고 펌웨어는 활성 폴더에서 제거하고 전체 백업에 유지.
- 사용자 요청으로 Pi 재부팅 완료. 재접속 후에도 Uno가 `lsusb`에 없고 `/dev/ttyACM*`/`ttyUSB*` 없음. 사용자에게 모터 전원을 끄고 외부 배선 분리 후 USB만, 다른 데이터 케이블/포트/PC 비교 시험을 안내했음. USB 포트 고장으로 단정하지 말 것.
- Pi 자동 테스트 90개와 ROS 도메인190 가상 주행/공개 참조 이미지 손 추종 통합 시험 통과. 실제 모터 출력은 하지 않았고 새 펌웨어는 업로드하지 않음.
- Pi에서 중복 SIGINT가 Node.destroy_node를 중단하는 문제를 재현하여 cleanup 구간에서 종료 신호를 잠시 무시하도록 수정. 실제 ROS 스모크 정상 종료/비상정지 확인.
- 카메라 OV5647 모델 인식 성공. ROS libcamera0.7.2는 ControlInfoMap 직렬화 오류, 시스템 libcamera0.2.0의 직접 cam 캡처도 prepareIsp buffers_.end assertion으로 실패. Picamera2 미설치. 실제 카메라 구동 성공으로 보고하지 말 것. 시험용 libcamera-v4l2는 실패 후 제거하여 남기지 않음.
- Pi의 기존 환경: Ubuntu 24.04, ROS 2 Jazzy, Raspberry Pi 4, Arduino Uno `/dev/ttyACM0`.
- 이전 실제 시험: `~/robot_ws/src/encoder_motor`의 Python EM2 두 모터 PWM 시험 성공. STBY=D10.
- 최신 구성: 드라이버 1 오른쪽 두 모터, 드라이버 2 왼쪽 두 모터. PWM/방향을 좌우 독립, 사용자 요청대로 STBY=D10 유지. 이전 D13 제안은 폐기하고 오른쪽 뒤 엔코더 A상을 D10에서 여유 핀 A2로 옮겼음. RR A/B=A2/A5, D13은 미사용. 새 펌웨어는 아직 업로드하지 않음.
- 새 주행 요구: 초록/빨강/좌/우 신호, 카메라 라인 추종, 초음파 우회, 손 위치/거리 추종.
- 손 모드는 가까우면 정지, 멀면 접근, 손을 놓치면 정지. 기본 거리는 손바닥 상대 면적이며 실제 cm는 보정 필요.
- 카메라 라인 프로필에서는 IR 입력을 쓰지 않고 A0/A1을 초음파 TRIG/ECHO에 사용. 이전 IR 3개 프로필도 WIRING.md에 보존.
- A2도 현재는 오른쪽 뒤 엔코더 입력이므로 IR 출력을 연결하지 말 것. IR 3개 프로필은 별도 재배선/펌웨어가 필요하며 현재 코드에서 지원하지 않음.
- 실제 엔코더 커넥터, 초음파 모델, 바퀴 치수/CPR/부호, 카메라 모델/설치 방향은 아직 실물 확인 전.
- 기본 하드웨어 출력은 꺼져 있고 0인 보정 값으로는 live 출력이 거부됨.
- **표지판 출처 정정:** 형제 `yolo_dataset`의 자료를 이번 프로젝트용 사용자 라벨로 잘못 판단했음. 사용자는 실제 사진/라벨을 제공하지 않았다고 정정함. 해당 실험과 이전 수치는 `experiments/unverified_workspace_dataset`에 분리, 기본 코드와 배포에서 제외. 원본 폴더는 수정하지 않음.
- 기본 표지판 처리는 학습 없는 색상/형상 방식. 테스트는 생성한 도형이며 실제 인식률은 미검증.
- 손 모델은 출처/라이선스가 기록된 OpenCV Zoo 공개 사전학습 모델.
- Windows 로컬 메모리 시험은 ROS/libcamera를 제외한 범위였음. 이후 Pi에서 ROS 통합 시험을 추가했으며 실제 카메라 구동/USB/실차/보정은 남아 있음. 최신 결과는 DEPLOYMENT_REPORT.md 및 artifacts/pi_deployment/ 참고.
- 최종 수치는 DEVELOPMENT_REPORT.md와 artifacts의 보고서를 확인할 것. `experiments`의 이전 숫자를 현재 검증 결과로 인용하지 말 것.

## SSH 복구 후 robot_ws 정리 — 사용자 요청

전체 코드 재점검에서 카메라·모델·시리얼·데모 임시 파일의 예외 경로 정리를 보강했다. 최신 재점검 수치는 `REFRACTOR_REPORT.md`와 `artifacts/memory_lifecycle_report.json`도 함께 확인한다. 수정 전 로컬 소스 백업 `artifacts/refactor_before_*.zip`은 원격 `robot_ws` 전체 백업을 대신하지 않는다.

사용자는 SSH가 다시 연결되면 기존 `~/robot_ws` 디렉터리 전체를 백업한 뒤 불필요한 파일을 삭제하도록 명시적으로 요청했다. 아래 절차로 이번 백업/정리를 완료했다. 이후 다시 정리할 때도 새 전체 백업과 무결성 검증을 먼저 수행한다.

1. `~/robot_ws`의 실제 경로, 심볼릭 링크, 실행 중인 노드와 디스크 여유를 확인한다. 모터를 정지시키고 작업 중 파일이 변경되지 않도록 한다.
2. 원본 바깥의 별도 디렉터리 `~/robot_ws_backup_YYYYMMDD_HHMMSS/`에 디렉터리 전체를 복사한다. 숨김 파일, 소스, 펌웨어, 기존 보드 백업, 설정 및 보정 자료를 포함한다. 기존 백업을 덮어쓰지 않는다.
3. 파일 목록/일반 파일 SHA-256, 심볼릭 링크 대상과 복사 오류를 확인하여 백업이 온전한지 검증한다. 공간 부족이나 검증 실패 시 삭제하지 않는다.
4. 파일 용도와 새 코드의 의존성을 조사한 뒤 `build/`, `install/`, `log/`, 캐시·임시 파일·중복 산출물 및 대체되어 쓰이지 않는 코드를 정리한다. 이름만으로 소스/모델/설정을 불필요하다고 판단하지 않는다. 삭제 경로가 원본 `robot_ws` 내부인지 검증하고 외부 링크 대상이나 백업에는 손대지 않는다.
5. 삭제 목록과 백업 경로를 작업 기록에 남기고, 정리된 워크스페이스를 다시 빌드하여 남은 코드와 실행 명령을 확인한다. 사용자에게 백업 위치·정리 내용·검증 결과를 보고한다.
