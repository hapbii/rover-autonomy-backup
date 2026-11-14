# ROS 2 전차형 로버 — Pi 모터 제어 / Uno 센서 입력

2026-11-13 배선 변경을 반영한 로컬 개발본입니다. **1번 TB6612=왼쪽 2개, 2번=오른쪽 2개.** Raspberry Pi 4가 하드웨어 PWM·방향·좌우 속도 PID를 담당하고 Arduino Uno가 엔코더 4개·초음파·IR 5개를 읽어 GPIO UART로 전송합니다.

**Pi 배포·ROS 빌드·가상 주행/손 추종 통합 시험과 PWM 0/정지 감시 확인은 완료했습니다. Uno 새 펌웨어 업로드·UART 실물 통신·실차 주행은 아직 완료하지 못했습니다.** 기본값은 `hardware.enabled: false`, `calibrated: false`, `idle`입니다. 이전 Pi 배포의 테스트 결과와 USB/카메라 문제는 역사 기록이며 이번 코드가 Pi에서 실행됐다는 뜻이 아닙니다.

## 최종 핀

GPIO는 BCM 번호입니다. 물리 핀·전원·센서 세부사항은 [WIRING.md](WIRING.md)를 기준으로 합니다.

| 입력 | 1번: 왼쪽 Pi GPIO | 2번: 오른쪽 Pi GPIO |
|---|---:|---:|
| PWMA | 12 | 13 |
| AIN2 | 3 | **23** |
| AIN1 | 4 | 5 |
| STBY | 17 | 6 |
| BIN1 | 27 | **9** |
| BIN2 | 22 | **11** |
| PWMB | 18 | 19 |

오른쪽 AIN2는 예약 GPIO0 대신 GPIO23에 연결합니다. 왼쪽 12/18과 오른쪽 13/19는 각각 같은 하드웨어 PWM 채널을 사용합니다. 입력선은 각 GPIO에 따로 연결합니다. GPIO 출력끼리 묶지 않습니다. 앞뒤 모터 방향은 독립이고 듀티는 같은 쪽에서 공유합니다.

| Uno 센서 | 핀 |
|---|---|
| LF 엔코더 A/B | D2/D4 |
| RF 엔코더 A/B | D6/D7 |
| LR 엔코더 A/B | A3/A4 |
| RR 엔코더 A/B | A2/A5 |
| 초음파 TRIG/ECHO | A0/A1 |
| IR 왼쪽→오른쪽 5개 | D8/D9/D10/D11/D12 |

드라이버 로직 VCC는 3.3V 지원 여부 확인 후 Pi 3.3V, VM은 외부 6V, GND는 모두 공통입니다. 센서는 모듈 정격에 맞는 전원을 사용합니다. IR은 디지털 출력형을 가정하며 `ir_active_low`를 실측합니다. **이전 보드 펌웨어는 센서 핀을 출력으로 사용하므로 센서 연결 전에 RA2를 올립니다.**

## 동작 구조

`camera_node → perception_node → supervisor_node → base_node → Pi PWM/방향 출력`

Uno RA2 센서 → GPIO14/15 UART → `base_node`에서 엔코더 RPM·위치 추정·좌우 PID·초음파 정지 게이트. Uno에는 속도·모터 ARM 명령을 보내지 않습니다. 통신 기본 포트는 `/dev/serial0`, 115200 baud입니다. Uno D1 TX는 5V→3.3V 변환 후 Pi GPIO15 RX에 연결하고 Pi GPIO14 TX는 Uno D0 RX로 연결합니다. 시리얼 식별 문자열이 다르거나 보드 재시작·센서 단절·제어 루프 지연이 발생하면 Pi 모터를 정지시키고 재연결·명시적 재활성화를 요구합니다.

| 모드 | 동작 |
|---|---|
| `idle` | 정지 |
| `line` | 카메라 라인 추종 + 초음파 기반 반응형 우회 |
| `autonomous` | 라인 추종 + 빨강 정지/초록 재개/좌·우 화살표 회전 + 우회 |
| `hand` | 손 위치로 조향, 손바닥 크기로 접근·정지, 손을 놓치면 정지 |

IR 5개는 모두 읽어 ROS에 공개합니다. **현재 라인 주행 판단은 계속 카메라 기준이며 IR 자동 전환은 추가하지 않았습니다.** 손 추종은 공개 사전학습 손바닥 모델을 사용하며 cm 단위 거리 유지는 실측 보정이 필요합니다. 장애물 우회는 전면 초음파와 차체 회전으로 공간을 비교하는 반응형 방식이며 지도 기반 경로 계획은 아닙니다.

## Pi 연결 후 적용

1. `~/robot_ws` 전체를 원본 밖의 새 폴더로 백업하고 파일을 검증합니다. 기존 전체 백업 `~/robot_ws_backup_20261112_094404`도 유지합니다.
2. 전송 묶음을 별도 스테이징 폴더에 풀어 비교 후 배포합니다. SSH/업로드를 수행했다고 가정하지 않습니다.
3. Uno USB 미인식과 기존 libcamera 오류를 점검합니다. I2C/SPI/오디오가 모터 GPIO를 점유하지 않게 설정을 확인합니다.
4. Python 의존성과 로컬 pigpiod를 준비하고 RA2 센서 펌웨어를 업로드합니다. 기존 펌웨어가 올라간 동안 D8~D12의 센서 신호는 분리합니다.
5. 모터 출력 없이 센서를 확인하고, 바퀴를 띄워 Pi PWM 벤치 시험을 수행합니다.
6. 치수·CPR·모터/엔코더 부호를 보정한 후 저속 자율주행을 시험합니다.

Pi Python 환경은 `requirements-pi.txt`를 사용합니다. 새 의존성 `pigpio`는 클라이언트이고 **pigpiod 실행 파일은 별도 설치**입니다. Pi 4의 OS·커널에 맞춰 [upstream 설치 안내](https://github.com/joan2937/pigpio/blob/master/README)를 확인합니다. 하드웨어 PWM은 pigpiod의 기본 PCM 클록이 필요합니다. 이미 실행 중인 데몬의 옵션을 확인하고, 새로 실행할 때는 로컬 접속만 허용할 수 있습니다.

```bash
sudo pigpiod -l
```

모터 프로세스는 데몬 자동 설치·자동 시작·부팅 시 자율주행을 수행하지 않습니다. 데몬 동작 확인 및 모터 비활성 상태에서 현장 검증이 필요합니다. 프로세스가 정지해도 살아 있는 pigpiod의 감시 스크립트가 STBY를 약 250ms 후 LOW로 내립니다. pigpiod/OS 자체 고장까지 보호하는 하드웨어 차단을 대신하지는 않습니다.

## Uno 센서 업로드·측정 (USB 업로드와 UART 실행 구분)

```bash
cd ~/robot_ws
~/.local/bin/arduino-cli compile --fqbn arduino:avr:uno firmware/rover_sensors
~/.local/bin/arduino-cli upload --fqbn arduino:avr:uno --port /dev/ttyACM0 firmware/rover_sensors
source ./env.sh
python scripts/encoder_probe.py --port /dev/serial0 --duration 20
```

`encoder_probe.py`는 Pi GPIO를 열지 않고 손으로 바퀴를 돌릴 때 LF/RF/LR/RR 계수·초음파·IR을 표시합니다. x1 출력축 1회전 계수를 측정합니다. 전진 시 음수라면 `encoder_signs`를 조정합니다. 실제 앞/뒤 A/B 채널과 전진 방향은 `motor_signs`(LF RF LR RR 순서)로 맞춥니다.

펌웨어 USB 업로드 시 Pi UART 선은 분리합니다. `/dev/ttyACM0`은 USB 업로드 연결이 인식될 때만 존재합니다. UART 14/15 두 선은 Uno 자동 리셋/DTR을 제공하지 않으므로 새 펌웨어 업로드 방법을 별도로 준비해야 합니다. UART 전압·배선·Pi 부팅 설정은 [WIRING.md의 UART 변경](WIRING.md)을 확인합니다.

## 모터 벤치 시험

Pi GPIO를 사용하는 ROS 노드로 변경했습니다. Uno 센서 RA2가 있어야 하며, 유효한 초음파 거리와 최신 통신이 없거나 130mm 이내면 구동하지 않습니다. `wheels_lifted:=true`는 사용자가 바퀴를 띄우고 즉시 전원 차단이 가능한 상태에서 지정합니다. 차체 치수를 몰라도 짧은 PWM 시험은 가능하지만 RPM 보정 완료를 뜻하지 않습니다.

```bash
source ./env.sh
bash scripts/build.sh
source install/setup.bash
ros2 run rover_autonomy motor_bench_test --ros-args -p wheels_lifted:=true -p pwm:=48 -p duration:=0.5
```

오른쪽 → 왼쪽 → 전체 순서의 유한 시험 후 정지합니다. 좌우 별도 방향/출력은 `-p right_pwm:=40 -p left_pwm:=-40`처럼 지정합니다. 벤치와 주행 노드는 같은 Pi GPIO를 동시에 소유하지 못하게 잠금을 사용합니다. 보고되는 PWM은 설정값이며 실제 회전은 엔코더·육안으로 확인합니다.

## 자율주행 실행

`rover.yaml`에 실측 `wheel_radius_m`, `track_width_m`, `encoder_ticks_per_rev`와 올바른 `encoder_signs`/`motor_signs`를 넣고 `calibrated: true`로 설정한 뒤 실행합니다. 치수 0 또는 미보정 상태에서는 실물 출력이 거부됩니다.

```bash
source ./env.sh
bash scripts/build.sh
source install/setup.bash
ros2 launch rover_autonomy rover.launch.py hardware_enabled:=true
```

다른 터미널에서 환경을 불러온 뒤 모드를 선택하고 활성화합니다.

```bash
ros2 topic pub --once /rover/mode std_msgs/msg/String "{data: autonomous}"
ros2 service call /rover/arm std_srvs/srv/SetBool "{data: true}"
ros2 service call /rover/arm std_srvs/srv/SetBool "{data: false}"
ros2 service call /rover/emergency_stop std_srvs/srv/SetBool "{data: true}"
```

모드는 `idle`, `line`, `autonomous`, `hand`입니다. 활성화에는 최신 영상·거리·준비된 베이스가 필요합니다. 비상정지 해제 후에도 명시적으로 재활성화해야 합니다. 영상/센서/명령 단절과 개별 엔코더 이상은 정지 처리합니다.

## 주요 토픽

| 토픽 | 내용 |
|---|---|
| `/rover/ir_raw` | IR 왼쪽→오른쪽 HIGH/LOW 5개 |
| `/rover/ir` | `ir_active_low` 적용 후 감지=1인 값 5개 |
| `/rover/encoder_counts` | LF RF LR RR uint32 계수 |
| `/rover/range` | 전면 초음파, 무효 시 NaN |
| `/rover/target_rpm`, `/rover/measured_rpm` | 오른쪽·왼쪽 RPM |
| `/rover/applied_pwm` | 오른쪽·왼쪽 PWM, 부호 포함, 255 기준 |
| `/rover/odom` | 엔코더 기반 위치/방향 추정 |
| `/rover/camera/compressed`, `/rover/vision` | 영상 및 인식 결과 |
| `/rover/state`, `/rover/base_state` | 주행/하드웨어 상태와 정지 이유 |

## 검증·파일

Windows 로컬에서는 `python -m pytest -q`, `python -m ruff check src tests scripts`, `python scripts/build_firmware.py`로 확인합니다. 새 코드의 시험·제한은 [PIN_MIGRATION_REPORT.md](PIN_MIGRATION_REPORT.md)에 기록합니다. Pi ROS·실제 PWM·센서/카메라·장시간 자원 사용 검증은 별도로 필요합니다.

`python scripts/package_for_pi.py`는 SHA-256 manifest를 포함한 `artifacts/rover_autonomy_pi_bundle.zip`을 생성합니다. 현재 RA2 hex만 포함하고 과거 RA1/EM2 바이너리와 실험 자료는 제외합니다.

| 위치 | 역할 |
|---|---|
| `hardware/pi_motors.py` | Pi 하드웨어 PWM·방향·감시·좌우 PID |
| `hardware/pi_drive.py` | 센서 피드백과 모터 상태·활성화 관리 |
| `hardware/sensor_protocol.py` | RA2 식별·센서 통신 |
| `firmware/rover_sensors/rover_sensors.ino` | Uno 센서 전용 펌웨어 |
| `hardware/legacy_protocol.py` | 이전 RA1의 오프라인 회귀시험 보존용, 현장 사용 안 함 |

## 인식 검증과 이전 기록

사용자는 실제 표지판 사진·라벨을 제공하지 않았습니다. 형제 `yolo_dataset`을 프로젝트 데이터로 잘못 참조했던 초기 실험은 `experiments/unverified_workspace_dataset`에 보존하고 기본 실행·배포에서 제외했습니다. 현재 기본 표지판은 HSV 색상/형상 방식이며 합성 도형 시험만 통과했습니다. 실제 카메라 인식률은 미검증입니다. 손 모델은 별도의 공개 OpenCV Zoo/MediaPipe 사전학습 모델이며 출처·라이선스는 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)에 있습니다.

[DEPLOYMENT_REPORT.md](DEPLOYMENT_REPORT.md), [DEVELOPMENT_REPORT.md](DEVELOPMENT_REPORT.md), [REFRACTOR_REPORT.md](REFRACTOR_REPORT.md)는 이전 Uno 모터 제어 시기의 결과입니다. 이전 배포 당시에는 Uno USB 미인식과 카메라 libcamera 오류가 남았습니다. 이번 작업에서 카메라를 수정하여 실제 ROS 영상 수신을 확인했습니다. Uno 펌웨어 업로드와 최신 모터 4개 구동은 아직 확인하지 못했습니다.

기존 비공개 GitHub 백업은 노트북 자료 기준이며 Pi에만 있는 전체 원본은 포함됐다고 가정하지 않습니다. 이번 로컬 수정도 아직 원격 저장소에 커밋·푸시하지 않았습니다.

## Ubuntu 카메라 수정본 — 실제 Pi 확인 완료

OV5647 캡처 시 발생하던 libcamera 0.2.0의 embedded-buffer 초기화 오류를 상위 수정에 따라 별도 소스 트리에서 보정했습니다. native 3프레임, 프로젝트 Python 30프레임(640×480), ROS 카메라 노드 20프레임 약 12fps와 정상 종료를 확인했습니다. 시스템과 ROS 기본 라이브러리는 덮어쓰지 않았습니다.

`source env.sh`는 검증한 빌드가 있는 경우에만 `scripts/camera_env.sh`를 통해 이 작업 공간의 Python/라이브러리 경로를 선택합니다. 지원 소스는 `~/rover_support/libcamera-v0.2.0-fixed`와 `~/rover_support/kmsxx`에 있고, Picamera2 0.3.17을 별도 Python 의존성으로 사용합니다.

새 Pi에서 재현할 때는 개발 도구·libgnutls28-dev·libevent-dev·libyaml-dev·libdrm-dev·libjpeg-dev·libcap-dev·python3-dev·python3-jinja2·pybind11-dev 등을 준비한 뒤 아래 순서로 실행합니다. KMS는 시험한 커밋으로 고정하며 디스플레이 시험 유틸리티는 빌드하지 않습니다.

```bash
source ./env.sh
python scripts/build_camera_stack.py
python -m pip install -r requirements-camera-pi.txt
source ./env.sh
python scripts/camera_smoke.py
```

카메라 시험은 카메라 노드만 실행하고 UART나 모터 출력을 열지 않습니다. 세부 적용·검증·남은 작업은 [UART_DEPLOYMENT_REPORT.md](UART_DEPLOYMENT_REPORT.md)를 확인합니다. Uno는 COM8에서 기존 EM2 응답이 확인되지만 부트로더 동기화가 실패하여 새 RA2 업로드는 아직 완료하지 못했습니다. 전체 배선 분리 비교가 현재 어렵다는 답변을 받아 재시도를 중단했습니다. UART 전압 변환 준비도 필요합니다.