# UART 전환·Pi 배포 기록 — 2026-11-13

## 적용한 구성

- Pi 접속: takyeji@192.168.50.34, Raspberry Pi 4 Model B Rev 1.5 / Ubuntu 24.04 / ROS 2 Jazzy.
- 활성 작업 공간: `/home/takyeji/robot_ws`.
- 배포 전 전체 백업: `/home/takyeji/robot_ws_backup_20261113_102324`. 일반 파일 1,503개, 98,909,936 bytes와 링크/디렉터리/FIFO 메타데이터 검증 완료.
- 모터 핀은 WIRING.md와 같으며 통신은 USB에서 GPIO UART로 변경. Pi GPIO14 TX(물리 8) → Uno D0 RX, Uno D1 TX → 5V/3.3V 변환 → Pi GPIO15 RX(물리 10), 공통 GND.
- 기본 포트 `/dev/serial0`, 115200 baud. 재부팅 후 `/dev/ttyAMA0` 장치 확인. Ubuntu에서 기본 별칭이 생성되지 않아 `/etc/udev/rules.d/99-rover-uart.rules`로 serial0 별칭과 dialout 권한을 설정함.
- `/boot/firmware/config.txt`와 `cmdline.txt`는 `/boot/firmware/rover_uart_backup_20261113_102720/`에 백업한 뒤 수정함. UART 로그인 콘솔 제거, enable_uart=1, disable-bt 오버레이. 모터 핀과 충돌하는 i2c_arm/SPI/아날로그 오디오 해제 후 재부팅·SSH 재연결 확인. Bluetooth UART는 재배정했고 Wi-Fi SSH는 유지됨.

## 검증한 항목

- 새 코드의 Pi ROS 빌드 성공. Pi의 초기 새 테스트 148개, 데몬 연결 실패 처리 보강 후 149개 통과. GPIO14/15를 모터 핀에서 예약한 최종 로컬 테스트는 150개 통과. **최종 Pi 재시험도 150개 통과**, Ruff 오류 없음.
- Pi에서 가상 주행 ROS 통합 시험 및 공개 참조 이미지 손 추종 통합 시험 각각 통과. 실제 모터 출력은 비활성화했고 거리 입력은 가상 값임.
- 공식 pigpio v79를 별도 support 폴더에서 빌드·설치. localhost만 허용해 실행함. 이 환경의 데몬은 IPv6 localhost에 바인딩되어 코드의 접속 주소를 127.0.0.1에서 localhost로 수정함.
- 실제 pigpiod에 PWM 0만 요청한 시험에서 STBY 17/6=LOW 확인. 하트비트 중단 뒤 감시 스크립트 종료·timeout latch=1 및 출력 재요청 거부 확인. 스크립트와 모터 연결은 시험 후 정리함.
- `hardware.enabled=false`, `calibrated=false` 유지. 비영(0이 아닌) PWM 명령·모터 벤치·실차 주행·실제 UART 개방은 수행하지 않음.
- 증거 파일은 `artifacts/uart_deployment/` 및 Pi의 `artifacts/`에 보관함.

## Uno 펌웨어 — 미완료

- 노트북에서 Arduino Uno COM8(2341:0043) 인식 확인. 사용자는 D0/D1 선 분리 및 모터 전원 OFF를 확인함.
- 기존 펌웨어 응답은 EM2 BOOT. flash/EEPROM 읽기와 공식 업로더의 업로드 시도는 STK500 부트로더 동기화 실패로 완료하지 못함. 업로드 성공·새 RA2 설치로 보고하지 않음. 기존 보드 전체 메모리를 새로 백업했다고도 가정하지 않음.
- 자동 리셋·수동 RESET·공식 avrdude 8.0/6.3 확인 후에도 증상이 지속됨. 전체 Uno 점퍼선/외부 전원을 분리하는 비교 시험을 제안했으나 사용자는 현재 어렵다고 답하여 추가 리셋·업로드 시도를 중단함.
- 새 RA2 소스와 컴파일된 hex는 준비됨. 기존 EM2 펌웨어는 엔코더/IR 5개의 새 센서 프로토콜을 제공하지 않으므로 이 문제가 해결되어야 실물 통합이 가능함.

## UART 전압 — 연결 전 준비 필요

사용자는 아직 레벨 변환을 사용하지 않는다고 알림. Uno TX 5V를 Pi RX에 직접 연결하면 안 된다고 안내했고, 연결돼 있으면 해당 선을 분리하도록 요청함. 레벨 변환기 또는 1kΩ/2kΩ 분압을 준비한 사실은 아직 확인되지 않았으므로 실제 UART 통신 시험을 보류함. Pi TX 3.3V → Uno RX 방향은 직접 입력하며 Uno 전원과 공통 GND가 필요함.

## 카메라

시스템 libcamera 0.2.0의 OV5647 인식은 성공하지만 캡처 시 ipa_base.cpp의 embedded buffer assertion을 재현함. 상위 프로젝트가 설명한 초기화 결함과 일치하여 v0.2.0에 `params.buffers.embedded = 0`을 추가하는 별도 빌드를 `~/rover_support/libcamera-v0.2.0-fixed`에 준비함. 시스템/ROS 라이브러리는 덮어쓰지 않음. 결과와 적용 방법은 이어지는 최종 카메라 검증 기록을 확인함.

원인 참고: https://lists.libcamera.org/pipermail/libcamera-devel/2024-January/040367.html

## 최종 카메라 검증

- 수정한 native libcamera에서 실제 OV5647 3프레임 캡처 성공.
- 프로젝트 `PiCamera`에서 640×480 RGB888 30프레임 수신·자원 해제 성공. 30프레임 전체 약 3.06초(초기 대기 포함), 영상 표준편차 약 73.98로 비어 있지 않은 영상 확인.
- 실제 `camera_node`의 ROS JPEG 토픽 20프레임을 약 12.06fps로 수신. 노드 정상 종료(exit 0), 모터 출력/UART 개방 없음.
- Python 모듈은 별도 빌드의 libcamera 0.2.0, Picamera2 0.3.17, PyKMS 시험 커밋 `e0d593d298a3590d306bdf850cf0295d078fbf73`를 사용함. `scripts/camera_env.sh`를 env.sh에서 불러 프로젝트에만 경로를 적용함.
- 재현용 `scripts/build_camera_stack.py`, `requirements-camera-pi.txt`, `scripts/camera_smoke.py`를 추가함. 기본 시스템/ROS libcamera를 교체하지 않음.

현재 남은 필수 작업은 Uno RA2 업로드 문제 해결, UART 5V→3.3V 레벨 변환 후 통신, 엔코더/센서 실측과 바퀴 치수 보정, 저출력 실차 시험입니다. 현재 활성 모터·자율주행 프로세스는 실행하지 않았습니다.
