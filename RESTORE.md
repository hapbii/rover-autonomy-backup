# 전체 백업 검증과 복원

이 저장소는 현재 프로젝트와 관련 참고 자료의 파일을 보존합니다. 소스만 제외 없이 고른 최소 배포본이 아니라 가상 환경, SDK, 캐시, 실험·검증 기록까지 들어 있습니다. `BACKUP_MANIFEST.json`에 각 파일의 원래 복원 경로와 크기·SHA-256 및 빈 디렉터리 정보가 있습니다.

## 1. 내려받아 내용 검증

Git과 Python 3.12 이상이 있는 컴퓨터에서:

```bash
git clone https://github.com/hapbii/rover-autonomy-backup.git
cd rover-autonomy-backup
python rover_autonomy_ws/tools/verify_github_backup.py --root .
```

검증 도구는 표준 라이브러리만 사용합니다. ROS, 카메라, Arduino, pip 패키지 없이 검사하며 모터를 구동하지 않습니다. `sha256_passed: true`와 검증한 파일 수를 확인합니다.

## 2. 원래 폴더 구조로 복원

기존 파일을 덮어쓰지 않도록 **아직 존재하지 않는 새 경로**를 선택합니다.

```bash
python rover_autonomy_ws/tools/verify_github_backup.py --root . --restore-to "D:/recovered_rover_project"
```

이 명령은 먼저 백업 파일을 전부 검사하고, manifest의 원래 상대 경로로 복사하며 원본 수정 시각을 설정합니다. 복사한 파일 해시도 다시 검사합니다. 새 경로 아래에 다음 구조가 재생성됩니다:

```text
recovered_rover_project/
  rover_autonomy_ws/
  yolo_dataset/                       # 출처 미확인 참고 데이터, 현재 학습 자료로 사용하지 않음
  output/picar_validation/
  tmp/pdfs/build_picar_report.py
  picar 진행사항 정리.pdf
  ADR012-V5.1_PiCar-B_MarsRover_SmartCarKit_for_RPi-20260407.zip
```

## 3. 개발 환경 재개

최신 소스와 현재 상태는 `rover_autonomy_ws/README.md`를 읽습니다. Windows의 기존 `.venv`는 Python 3.12 기반입니다. 설치 경로나 운영체제가 바뀌면 OS에 맞는 Python으로 새 가상 환경을 만들고 requirements를 설치합니다. Linux/Pi에서 Windows용 `.exe/.pyd/.venv`를 그대로 실행하지 않습니다.

현재 Pi는 접근할 수 없어 Pi의 전체 `robot_ws` 원본, Git 이력, 원본 flash/EEPROM 백업 자체는 이 저장소에 새로 내려받지 못했습니다. 해당 파일은 Pi에서 별도 추가 백업해야 합니다. 내려받아 둔 JSON/로그는 디렉터리 전체 원본과 다릅니다.

소스의 오래된 ZIP과 최신 소스도 구분합니다. `motor_bench_test` 등 후속 변경까지 담으려면 현재 소스로 새 배포 묶음을 생성합니다. 하드웨어 작업은 사용자의 재배선 대기로 중단한 상태입니다.

## 무결성과 Git

현재 백업의 개별 파일은 GitHub의 일반 파일 한도 안에 있습니다. [GitHub 파일 크기 안내](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)

이 백업은 원본 `.gitignore`에서 제외하던 파일도 명시적으로 추적합니다. `.gitattributes`는 줄바꿈 정규화를 꺼서 원본 파일 바이트를 보존합니다. GitHub에서 별도로 clone한 복사본과 복원본을 검증한 결과는 `BACKUP_VERIFICATION.json`에 기록합니다.

복원 도구와 모든 명령은 원래 노트북 폴더를 삭제하지 않습니다. 이 저장소에 포함하지 않은 다른 프로젝트·전자회로 자료는 백업 범위 밖입니다.
