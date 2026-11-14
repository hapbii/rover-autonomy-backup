# ROS 2 로버 — 비공개 전체 파일 백업

2026-11-15 기준 **노트북의 변경 내용**을 기존 백업 이력에 이어 보존했습니다. 코드뿐 아니라 프로젝트 폴더의 실행 환경·SDK·캐시·모델·실험·로그·배포 ZIP도 포함하는 복구용 스냅샷입니다. 기존 참고 자료와 이전 커밋은 유지합니다.

사용자는 이번에는 노트북 변경 내용부터 백업하도록 지정했습니다. Pi SSH가 응답하지 않아 **Pi에만 있는 원본 폴더·부팅 설정은 이번 커밋에 포함되지 않습니다.** Pi에서 이미 노트북으로 받은 검증 기록과, 카메라 지원 환경을 재현하는 스크립트는 포함합니다.

## 이번에 반영한 내용

- 모터 제어를 Uno에서 Pi로 이동: 1번 드라이버=왼쪽, 2번=오른쪽. 왼쪽 PWM GPIO12/18, 오른쪽 GPIO13/19, 오른쪽 BIN1=9/BIN2=11, AIN2는 예약 GPIO0 대신23.
- Pi 좌우 속도 PID, 모터별 방향 부호, 개별 엔코더 이상 감시, 정지 인터록, pigpiod 하트비트 감시와 연결 오류 처리.
- Uno RA2 센서 전용 펌웨어 및 프로토콜: 엔코더 4개·초음파·IR 5개. 이전 Uno 모터 스케치 경로는 잘못 업로드하지 않도록 빌드 차단.
- Pi/Uno 통신을 GPIO UART로 변경: GPIO14 TX→Uno D0 RX, Uno D1 TX→5V/3.3V 변환→GPIO15 RX. 기본 포트 `/dev/serial0`, 115200 baud.
- IR 원시/감지 ROS 토픽, 새 Pi 모터 벤치 노드, 설정·배선표·진행 상태·펌웨어 업로드 시도 로그.
- Ubuntu libcamera 0.2.0의 embedded-buffer 초기화 문제를 별도 소스 빌드로 수정한 재현 스크립트, 선택 Python 의존성과 작업 공간 전용 카메라 환경 설정.
- Pi 배포·ROS 통합·실제 카메라·PWM 0/정지 감시 검증 기록, 최신 소스 전송 ZIP 및 SHA-256 manifest.

YOLO 다중 객체 검출은 대화에서 사용법을 설명한 상태입니다. 이번에 새 표지판 모델을 학습하거나 YOLO를 실차에 연동했다고 가정하지 않습니다. 기존 출처 미확인 `yolo_dataset`은 참고 자료로만 보존합니다.

## 마지막으로 확인한 실행 상태

아래는 2026-11-13 작업의 검증 기록이며 이번 백업 작업에서 하드웨어를 다시 실행한 결과가 아닙니다.

- 로컬/Pi 테스트 각각 **150개 통과**, Ruff 통과, Pi ROS 빌드 성공.
- 가상 주행·공개 참조 이미지 손 추종 ROS 통합 시험 통과. 실제 모터 출력 비활성.
- 실제 OV5647: native 3프레임, 프로젝트 Python 30프레임, ROS 카메라 토픽 20프레임 **약 12fps** 확인 및 정상 종료.
- 실제 pigpiod에 PWM 0만 요청해 STBY LOW·감시 시간 초과·출력 재요청 거부 확인.
- **Uno에는 아직 기존 EM2 펌웨어가 남아 있습니다.** COM8에서 인식됐으나 부트로더 동기화 실패로 새 RA2 업로드 미완료. 전체 배선 분리 비교가 현재 어렵다는 답변에 따라 추가 시도를 멈췄습니다.
- UART 5V→3.3V 변환 준비와 실제 UART 통신, 센서·바퀴 치수 보정, 모터 실차 시험은 미완료입니다. `enabled=false`, `calibrated=false` 유지.

최신 상세 내용은 [프로젝트 README](rover_autonomy_ws/README.md), [배선표](rover_autonomy_ws/WIRING.md), [UART/Pi 배포 기록](rover_autonomy_ws/UART_DEPLOYMENT_REPORT.md), [전환 기록](rover_autonomy_ws/PIN_MIGRATION_REPORT.md)를 기준으로 합니다.

## 백업 범위와 무결성

- 전체 manifest: **10,797개 파일, 1,122,865,308 bytes**.
- 이번에 노트북 원본에서 해시를 계산한 파일: **10,797개**.
- Git 인덱스의 파일 내용 ID 대조: **10,797개**.
- 이전 스냅샷 대비 원본 파일 변경: 추가 **609**, 수정 **44**, 삭제 반영 **0**. 원본 폴더에서 파일을 삭제한 작업은 아닙니다.
- 이전 커밋 `d40d26ced509cefe39ecfcdcd181640dcfd05c65`을 부모로 유지합니다. 삭제 반영된 파일의 이전 버전도 과거 커밋에 남습니다.
- `.gitattributes`로 줄바꿈 변환을 끄고 원본 바이트를 보존했습니다. 원본의 빈 디렉터리와 수정 시각은 manifest에 기록합니다.
- 현재 원본/복사본 SHA-256과 Git 파일 내용 ID를 대조했습니다. 사용자의 이전 중단 요청을 존중하여 전체 원격 clone·복원 시험은 다시 수행하지 않았습니다. GitHub 반영은 원격 브랜치의 커밋 ID로 확인합니다.

| 경로 | 내용 |
|---|---|
| `rover_autonomy_ws/` | 현재 노트북 프로젝트 전체, `.venv`·tools·SDK·캐시·과거 실험 포함 |
| `references/unverified_original_yolo_dataset/` | 출처/적합성 미확인 과거 참고 데이터 |
| `references/picar_validation_history/` | 기존 PiCar 코드·실험·환경 |
| 기타 `references/` | 기존 PiCar 원본 ZIP·PDF·보고서 생성 코드 |

전자회로 과제나 다른 로봇 등 무관한 상위 폴더는 포함하지 않습니다. Pi의 다음 원본은 별도 백업이 필요합니다: `~/robot_ws`, 기존 전체 백업 폴더들, `~/rover_support`의 libcamera/kmsxx/pigpio 소스·빌드, `/boot/firmware` 변경 및 백업, UART udev 규칙. 노트북의 재현 스크립트와 검증 JSON을 그 원본 자체와 혼동하지 않습니다.

## 복원

```bash
git clone https://github.com/hapbii/rover-autonomy-backup.git
cd rover-autonomy-backup
python rover_autonomy_ws/tools/verify_github_backup.py --root .
```

원래 폴더 구조로 복사하려면 아직 존재하지 않는 새 폴더를 지정합니다.

```bash
python rover_autonomy_ws/tools/verify_github_backup.py --root . --restore-to "D:/recovered_rover_project"
```

[복원 안내](RESTORE.md), [파일별 SHA-256 목록](BACKUP_MANIFEST.json), [백업 감사 기록](BACKUP_AUDIT.json), [검증 범위](BACKUP_VERIFICATION.json)를 확인합니다. Windows `.venv`는 경로/운영체제에 의존하므로 Pi에서는 적절한 Python 환경을 다시 구성합니다. 복원 직후 임의로 모터를 활성화하지 않습니다.
