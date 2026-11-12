# PiCar-B 오프라인 검증 자료

원본 ZIP과 `picar 진행사항 정리.pdf`는 수정하지 않았습니다. `original_hashes.json`과 `validation_summary.json`에서 SHA-256 일치를 확인할 수 있습니다.

## 결과

- 원본 코드 시험 136건: 통과 98, 문제 재현 31, 동작/환경 관찰 7. 여러 시험이 같은 원인을 다루므로 문제 31개라는 뜻은 아닙니다.
- 호환성 프로브 15건: 원래 시작 방식, 실행 중 루프만 적용, 루프와 함수 인자를 함께 조정한 경우를 비교했습니다.
- 복사본의 한정된 수정안 시험 14건: 모두 통과. 전체 문제를 해결한 배포본은 아닙니다.
- 핵심 시험은 Windows의 Python 3.13.5에서 수행했습니다. 실제 라즈베리파이 Debian/ARM 환경을 부팅한 시험은 아닙니다.

## 폴더

- `source/`: ZIP에서 추출한 비교 기준 코드. Python 원문은 ZIP과 바이트 단위로 같습니다.
- `working_copy/ADR012-....zip`: 사용자의 지시에 따라 만든 원본 ZIP 전체 복사본. 압축 파일 자체는 변경하지 않았습니다.
- `working_copy/code/`: 전체 ZIP 복사본에서 추출한 작업 코드. 네 파일의 후보 수정만 이곳에 있습니다.
- `candidate_fixes.patch`: HOME 복귀, 음수 대기 시간, 거리 읽기 반복 제한, 카메라 이벤트 메서드의 수정 비교.
- `results.json`: 원본 코드 시험별 입력, 관찰값, 예외, 주의 범위.
- `compat_results.json`: Python / websockets 비교 결과.
- `candidate_results.json`: 복사본 수정 후 시험 결과.
- `validation_summary.json`: 전체 집계와 원본 보존 확인.
- `requirements-test.txt`: 이번 Python 3.13.5 시험 패키지 버전 목록. Pi에 그대로 설치하라는 목록이 아닙니다.
- `collect_picar_diagnostics.sh`: Pi의 서비스·로그·버전·장치 경로 수집. 설치, 재부팅, 모터 동작 명령은 없습니다. `bash -n` 문법 검사만 PC에서 완료했습니다.

## 이 PC에서 재실행

현재 폴더를 이 README가 있는 폴더로 바꾼 뒤 실행합니다.

```powershell
.\.venv313\Scripts\python.exe .\run_tests.py
python .\run_compat_matrix.py
.\.venv313\Scripts\python.exe .\test_candidate_fixes.py
```

`run_tests.py`는 설치 스크립트의 외부 명령을 가짜 OS/프로세스/파일시스템으로 대체한 상태에서만 실행합니다. 실제 apt/pip, 시스템 서비스 변경, 재부팅은 실행하지 않습니다. 실제 하드웨어 라이브러리의 I2C 입출력도 메모리 모델로 대체됩니다. GPIO와 카메라 동작은 물리적으로 시험하지 않았습니다.

`test_candidate_fixes.py`는 재실행 때 네 후보 파일을 전체 ZIP 복사본에서 다시 꺼내 수정하고 결과를 덮어씁니다. 원본 ZIP 및 비교 기준 `source/`는 수정하지 않습니다.

모의 출력값은 실제 바퀴 속도, 이동 거리, 조향 각도 측정값이 아닙니다. 로컬 통신 통과는 Pi에서의 접속·배선·전원·센서 상태를 보증하지 않습니다. 상세 판단과 대응 순서는 함께 제공된 PDF를 참고하십시오.
