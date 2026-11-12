# 전차형 ROS 2 로버 — 비공개 전체 파일 백업

노트북의 기존 작업 폴더를 삭제하기 전에 현재 로버 프로젝트와 관련 참고 자료를 보존하기 위한 저장소입니다. **운영용 최소 소스 저장소가 아니라, 실행 환경·도구·캐시·과거 실험까지 포함하는 복구용 스냅샷**입니다. 저장소 공개 범위는 private입니다.

프로젝트의 전체 진행 상황·배선·명령어·검증 기록은 [프로젝트 README](rover_autonomy_ws/README.md)에 정리했습니다. 이 문서에는 백업 범위와 재개 지점을 요약합니다.

## 복구할 때 먼저 확인

```bash
git clone https://github.com/hapbii/rover-autonomy-backup.git
cd rover-autonomy-backup
python rover_autonomy_ws/tools/verify_github_backup.py --root .
```

파일별 SHA-256이 모두 맞는지 검사합니다. 원래 상위 작업 폴더의 상대 경로로 복원하려면 **존재하지 않는 새 폴더**를 지정합니다:

```bash
python rover_autonomy_ws/tools/verify_github_backup.py --root . --restore-to "D:/recovered_rover_project"
```

이 명령은 `rover_autonomy_ws`, 원래의 `yolo_dataset`, `output/picar_validation` 및 참고 파일 경로를 manifest대로 재구성하고 복사본 해시를 다시 확인합니다. [자세한 복원 안내](RESTORE.md), [파일별 원본/복원 목록](BACKUP_MANIFEST.json), [원격 복원 검증 기록](BACKUP_VERIFICATION.json)을 함께 확인합니다.

## 백업에 들어가는 것

| 저장소 경로 | 보존 내용 |
|---|---|
| `rover_autonomy_ws/` | 현재 로버 프로젝트 폴더의 모든 파일. 소스, ROS 설정/launch, RA1/EM2 펌웨어, 모델/라이선스, 테스트/합성 자료, 보고서/로그/영상/ZIP, tools, SDK, 가상 환경, 캐시, 과거 실험 포함 |
| `references/unverified_original_yolo_dataset/` | 과거 실험에서 참조한 원본 데이터와 라벨. 출처/현재 프로젝트 적합성 미확인 자료로 격리 보관 |
| `references/picar_validation_history/` | 기존 PiCar 참고 코드, 수정본, 검증 기록과 해당 실행 환경 전체 |
| `references/PiCar_B_MarsRover_vendor_20260407.zip` | 기존 작업 폴더에 있던 PiCar 참고 ZIP 원본 |
| `references/picar_progress.pdf` | 기존 PiCar 진행사항 PDF |
| `references/build_picar_report.py` | 해당 PDF 생성 코드 |

기존 `.gitignore`가 가상 환경 등을 제외하도록 되어 있어도 이 **백업 커밋에는 그 파일들까지 명시적으로 포함**합니다. 원본의 빈 디렉터리는 manifest에 기록하여 복원 도구가 재생성합니다. Git의 줄바꿈 변환을 끄고 파일 내용 그대로 보존합니다.

원본 파일은 총 **10,188개, 1,105,596,286 bytes(약 1.11GB / 1.03GiB)**입니다. Git 메타데이터와 이 저장소의 백업 안내·검증 보고서는 이 수치와 별도입니다. 현재 ROS 소스 `rover_autonomy_ws/src`는 약 4.21MB이고, 전체 크기 대부분은 함께 보존한 환경과 도구입니다. 아래 MB는 1,000,000 bytes 기준이며 Git 압축 전 파일 합계입니다.

| 항목 | 크기 |
|---|---:|
| 현재 프로젝트의 Arduino 도구·SDK·캐시 `tools` | 458.33MB |
| 현재 프로젝트의 Python 가상 환경 `.venv` | 237.26MB |
| 과거 PiCar 검증 코드·결과·실행 환경 | 258.84MB |
| 별도 PiCar 원본 참고 ZIP | 60.49MB |
| 보관된 과거 실험 | 39.98MB |
| 출처 미확인 원본 참고 데이터 | 37.38MB |
| 현재 ROS 소스 `src` | 4.21MB |
| 그 밖의 문서·펌웨어·테스트·산출물 | 약 9.11MB |

**Pi에만 있는 전체 원본은 포함되지 않습니다.** 이번 백업 시점에는 Pi SSH가 시간 초과됐고, 사용자는 노트북 자료를 먼저 백업하도록 지시했습니다. Pi에서 내려받은 일부 소스/로그/검증 JSON과 Pi 전체 디렉터리 원본은 구분해야 합니다. Pi의 아래 경로는 장비가 다시 가능해지면 별도로 추가 백업해야 합니다:

- `/home/takyeji/robot_ws`
- `/home/takyeji/robot_ws_backup_20261112_094404` 및 그 manifest/verification
- Uno 원본 flash/EEPROM 백업: `~/robot_ws/firmware/backups/uno_before_two_motor_20261111_113701/`

전자회로 과제나 다른 로봇 등 로버와 무관한 상위 폴더 전체를 백업한 저장소는 아닙니다. 노트북 원본 파일 삭제는 이 작업에서 실행하지 않았습니다.

## 현재 하드웨어와 최신 배선

Pi 4 / Ubuntu 24.04 / ROS 2 Jazzy / Uno / TB6612FNG 두 개 / FIT0450 모터 네 개 / 모터 전원 6V입니다. Pi↔Uno는 USB 시리얼입니다.

| 입력 | 1번 드라이버: 오른쪽 앞·뒤 | 2번 드라이버: 왼쪽 앞·뒤 |
|---|---|---|
| PWMA + PWMB | D3 | D5 |
| AIN1 + BIN1 | D9 | D11 |
| AIN2 + BIN2 | D8 | D12 |
| STBY | D10 | D10 |

두 입력은 각 드라이버 안에서 묶고 좌우 PWM·방향은 분리합니다. 각 보드 AO 출력은 앞 모터, BO 출력은 뒤 모터에 각각 연결합니다. VCC=Uno 5V, VM=외부 6V+, GND=외부 전원−와 Uno 공통입니다. 출력끼리 묶거나 6V를 Uno 5V 핀에 넣지 않습니다.

엔코더 A/B는 LF D2/D4, RF D6/D7, LR A3/A4, RR A2/A5입니다. 초음파 TRIG=A0, ECHO=A1이고 D13은 비워 둡니다. **STBY=D13의 이전 제안은 폐기했으며 최종은 D10**입니다. 현재 카메라+초음파 구성에서 IR 출력을 A0/A1/A2에 함께 연결하지 않습니다. [상세 배선](rover_autonomy_ws/WIRING.md)

## 구현과 검증 상황

- 라파 Python: 카메라 라인/색상·형상 표지판/사전학습 손바닥 검출, 정지 우선 판단, 좌우 목표 RPM 계산.
- Uno RA1: 엔코더 4개 x1 계수, 좌우 평균 RPM PID, 전면 초음파, watchdog, 모터 두 그룹 구동.
- 모드: idle / line / autonomous / hand. 빨강 정지 유지, 초록 연속 확인으로 해제, 화살표는 기본 90도 엔코더 추정 회전. 손 모드는 명시적 모드 선택이며 기본 거리 제어는 손바닥 상대 크기입니다.
- 실제로 성공을 확인한 구동은 **이전 EM2 두 모터 시험**입니다. 모터 4개 실차 시험은 아직 성공했다고 확인하지 않았습니다.
- 최신 자동 테스트 **로컬/Pi 각각 111개 통과**. Pi의 최초 배포 기록 90개는 그 이전 시점이며, 이후 벤치 시험 21개가 추가됐습니다.
- ROS 가상 주행과 공개 참조 이미지 손 추종: 별도 도메인190, 가상 거리, 실제 모터 출력 비활성으로 통과. 비상정지와 정상 종료 확인.
- RA1 Uno 컴파일: Windows/Pi 성공, 프로그램 12,782 bytes / 정적 RAM 549 bytes. 새 펌웨어 업로드는 아직 안 했습니다.
- Windows 연속 30,000회 메모리 시험: Python +0.027MiB / RSS +1.062MiB. 모델·파일 디코더 400회 재시작: Python +0.018MiB / RSS −0.004MiB. 지정 조건에서 지속 누적 징후 없음. Pi DDS/libcamera/실물 USB 전체의 장기 누수 검증 결과는 아닙니다.
- 초기 짧은 재시작 시험의 스레드 증가, 자원 정리 누락 재현과 수정, ARM/disarm 경합, 중복 종료 신호 보호는 [리팩터링 기록](rover_autonomy_ws/REFRACTOR_REPORT.md)에 남아 있습니다.

## 최신 중단 지점과 다음 작업

사용자가 바퀴 네 개를 띄우고 즉시 전원을 끌 수 있다고 확인한 뒤 아래 실제 ROS 명령을 실행했습니다:

```bash
source ~/robot_ws/env.sh
ros2 run rover_autonomy motor_bench_test --ros-args \
  -p wheels_lifted:=true -p pwm:=48 -p duration:=0.5
```

이것은 **EM2용 짧은 PWM 시험**이며 오른쪽 두 개 → 왼쪽 두 개 → 네 개 동시 → 정지 순서입니다. RA1의 보정 검사를 해제하는 기능이 아닙니다. 현재 배선에서는 정확한 EM2/STBY10 식별을 먼저 확인해야 합니다. T 응답은 출력 설정 확인이며 모터 회전을 측정한 결과가 아닙니다.

실제 실행 결과는 `/dev/ttyACM0` 미존재 오류였고 **모터 명령은 전송되지 않았습니다.** USB 포트를 옮겨도 전원 LED만 켜지고 장치가 보이지 않았습니다. 사용자 요청으로 재부팅했지만 증상이 같았습니다. USB 허용 설정은 켜져 있었고 새로운 Uno USB 연결 이벤트가 없었습니다. 케이블/포트/보드/배선 중 원인은 미확정입니다.

사용자는 전체 배선을 다시 하겠다며 대기를 요청했습니다. **현재는 하드웨어 작업 중단 상태**이며 임의로 모터 시험이나 펌웨어 업로드를 재개하지 않습니다. 재개 시에는 USB만 연결해 다른 데이터 케이블/다른 PC로 인식을 비교하고, 실제 펌웨어·배선과 바퀴 상태를 확인한 뒤 짧은 시험부터 진행합니다.

카메라는 OV5647로 감지되지만 ROS libcamera0.7.2는 ControlInfoMap 직렬화 오류, 시스템 libcamera0.2.0 직접 캡처도 prepareIsp 버퍼 assertion으로 영상 획득에 실패했습니다. Picamera2 미설치이며, 시험용 V4L2 호환 패키지는 제거했습니다. 실제 카메라 구동 성공이나 실차 자율주행 성공으로 표현하지 않습니다.

이후 엔코더 단자/부호/CPR, 바퀴 반지름·좌우 간격, 초음파 모델/전압, 카메라 스택을 확인해야 합니다. 기본 `hardware.enabled=false`, `calibrated=false`, 치수/CPR=0을 유지합니다. 실제 측정 없이 값을 꾸며 넣지 않습니다.

## 표지판 데이터 출처 정정

사용자는 이번 프로젝트용 사진/라벨을 제공하지 않았습니다. 초기에 기존 형제 `yolo_dataset`을 이번 프로젝트 자료로 잘못 판단한 실험과 성능 수치는 철회했고, 파생 자료는 `experiments/unverified_workspace_dataset`에 격리했습니다. 원본도 이번 **복구 백업**의 references에 보관하지만 기본 인식/배포/시험 성능의 근거로 사용하지 않습니다.

현재 표지판 처리는 학습 없는 색상·형상 방식이며 합성 도형 162조건만 확인했습니다. 실제 사진 인식률은 미검증입니다. 손 모델은 별개로 공개 OpenCV Zoo 사전학습 palm 모델이며 출처·라이선스가 프로젝트에 있습니다.

## 보존 파일 사용 시 구분

- **최신 작업본:** `rover_autonomy_ws/src`, `firmware`, `scripts`, 문서 전체.
- `artifacts/rover_autonomy_pi_bundle.zip`과 배포 해시는 과거 전송 시점의 산출물입니다. 이후 벤치 코드가 추가됐으므로 다시 배포할 때는 현재 소스에서 묶음을 새로 생성해야 합니다.
- 가상 환경/SDK도 보존했지만 Windows/Python 버전이나 설치 경로가 달라지면 `requirements-dev.txt` 또는 `requirements-pi.txt`로 환경을 재생성해야 할 수 있습니다. 이 저장소는 OS 전체 이미지가 아닙니다.
- 상세 기록: [Pi 배포](rover_autonomy_ws/DEPLOYMENT_REPORT.md), [개발](rover_autonomy_ws/DEVELOPMENT_REPORT.md), [작업 상태](rover_autonomy_ws/docs/PROJECT_STATE.md).
