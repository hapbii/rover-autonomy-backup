# 최종 배선 — 2026-11-13

이 문서의 GPIO는 **BCM 번호**입니다. 괄호 안 숫자는 Pi 40핀 헤더의 물리 핀입니다.
**1번 드라이버=왼쪽 앞·뒤, 2번=오른쪽 앞·뒤.** Pi가 모터·좌우 PID를 제어하고 Uno가 엔코더 4개·초음파·IR 5개를 읽습니다. 실제 결선·구동은 아직 확인하지 않았습니다.

## Raspberry Pi 4 → TB6612FNG 2개

| 드라이버 입력 | 1번: 왼쪽 GPIO (물리 핀) | 2번: 오른쪽 GPIO (물리 핀) |
|---|---|---|
| PWMA | GPIO12 (32) | GPIO13 (33) |
| AIN2 | GPIO3 (5) | **GPIO23 (16)** |
| AIN1 | GPIO4 (7) | GPIO5 (29) |
| STBY | GPIO17 (11) | GPIO6 (31) |
| BIN1 | GPIO27 (13) | **GPIO9 (21)** |
| BIN2 | GPIO22 (15) | **GPIO11 (23)** |
| PWMB | GPIO18 (12) | GPIO19 (35) |

- 오른쪽 BIN1=GPIO9, BIN2=GPIO11은 사용자의 최종 지정값입니다.
- 오른쪽 AIN2는 원래 지정한 GPIO0(HAT EEPROM 예약 핀) 대신 GPIO23으로 배정했습니다. **실제 선도 GPIO23에 연결해야 코드와 일치합니다.**
- 왼쪽 GPIO12/18은 PWM0, 오른쪽 GPIO13/19는 PWM1을 공유합니다. 코드는 같은 쪽 두 핀에 같은 주파수와 듀티를 설정합니다. **각 입력을 표의 GPIO에 따로 연결하며 Pi GPIO 출력끼리 선으로 묶지 않습니다.**
- AO1/AO2 → 해당 쪽 앞 모터, BO1/BO2 → 해당 쪽 뒤 모터를 기준으로 합니다. 실제 앞/뒤 대응을 확인합니다. 드라이버 출력끼리는 묶지 않습니다.
- 방향 입력은 A/B별로 분리되어 있습니다. 실제 설치 방향은 `motor_signs`로 바꿀 수 있습니다. PWM이 같아도 기계적 부하 차이 때문에 앞뒤 실제 RPM이 완전히 같다는 뜻은 아닙니다. PID는 좌우 각각 1개이고 엔코더 이상 감시는 4개 각각 수행합니다.

## Arduino Uno → 엔코더·초음파·IR

| 센서 | 신호 | Uno 핀 |
|---|---|---|
| 왼쪽 앞 LF 엔코더 | A / B | D2 / D4 |
| 오른쪽 앞 RF 엔코더 | A / B | D6 / D7 |
| 왼쪽 뒤 LR 엔코더 | A / B | A3 / A4 |
| 오른쪽 뒤 RR 엔코더 | A / B | A2 / A5 |
| 초음파 | TRIG / ECHO | A0 / A1 |
| IR 1 — 차량 전진 기준 왼쪽 끝 | OUT | D8 |
| IR 2 | OUT | D9 |
| IR 3 — 중앙 | OUT | D10 |
| IR 4 | OUT | D11 |
| IR 5 — 오른쪽 끝 | OUT | D12 |

센서는 사용자가 남는 핀 배정을 맡겨 위와 같이 정했습니다. 기존 엔코더 배선을 유지합니다. D0/D1은 Pi와의 GPIO UART 전용이며 D3/D5/D13은 남습니다. Pi GPIO9와 Uno D9처럼 번호가 같아도 서로 다른 보드의 핀입니다.

초음파는 TRIG/ECHO형, IR은 SEN200621의 디지털 OUT 5개를 가정합니다. 실제 초음파 모델·전원·IR 출력 규격을 확인해야 합니다. IR이 아날로그 출력 전용이면 D8~D12 대신 ADC 입력을 사용하는 재배정이 필요합니다. `ir_active_low: true`는 검정 감지 시 LOW라는 가정이며 실물 확인 후 변경합니다.

엔코더는 A상 상승 에지(x1)를 세고 B상으로 방향을 구분합니다. 실제 출력축 한 바퀴 계수와 `encoder_signs`를 확인합니다. 모터 구동선과 엔코더 전원/신호를 구분하고 실제 모듈의 단자 표시를 확인합니다.

## 전원·통신

| 대상 | 연결 |
|---|---|
| 두 드라이버 VCC (로직) | **Pi 3.3V**, 모듈의 3.3V 로직 전원 지원 확인 |
| 두 드라이버 VM (모터 전원) | 외부 6V + |
| GND | Pi·Uno·드라이버·외부 전원 −·센서 공통 |
| 엔코더·초음파·IR VCC | 모듈 정격에 맞는 전원. 5V형은 Uno 5V 공급 여력 확인 |
| Pi ↔ Uno | GPIO14 TX → Uno D0 RX, Uno D1 TX → 3.3V 변환 → GPIO15 RX |

이전 드라이버 VCC=Uno 5V 배선은 변경합니다. TB6612 HIGH 입력 최소값은 0.7×VCC이므로 5V 로직 전원에서 Pi 3.3V HIGH는 보장되지 않습니다. 드라이버 모듈이 3.3V 로직 전원을 지원하지 않으면 적절한 레벨 변환이 필요합니다. 센서 5V 출력은 Uno에 연결하고 Pi GPIO에 직접 연결하지 않습니다. 외부 6V는 모터 VM에 공급합니다.

STBY는 초기화·종료 시 LOW입니다. Pi 제어 루프 중단 시 로컬 pigpiod의 감시 스크립트가 약 250ms 후 두 STBY를 LOW로 내리고 고장을 유지하도록 구현했습니다. 이 동작은 pigpiod와 OS가 동작하는 조건이며 실물 검증이 남아 있습니다. 부팅/전원 이상 시 STBY를 LOW로 유지하려면 각 STBY에 외부 풀다운(예: 10kΩ)을 추가하는 것을 권장합니다.

## 소프트웨어 적용 상태

- 설정: `src/rover_autonomy/config/rover.yaml`의 Pi 핀과 센서 전용 RA2 통신 반영.
- Uno 펌웨어: `firmware/rover_sensors/rover_sensors.ino` — 모터 출력 없음. D8~D12는 입력.
- 이전 `rover_camera`/`motor_bench` 경로는 빌드를 차단하고 새 `rover_sensors` 경로를 안내합니다. 이전 모터 핀을 출력하는 바이너리를 새로 만들지 않습니다.
- **현재 보드에 남아 있는 이전 RA1/EM2 펌웨어는 D8~D12를 모터 출력으로 사용합니다. 센서 신호 연결 전에 새 RA2 펌웨어를 업로드합니다.**
- Pi 배포·ROS 빌드·UART 설정과 pigpiod의 PWM 0/정지 감시 검증을 완료했습니다. I2C(GPIO3)·SPI(GPIO9/11)·아날로그 오디오는 해제했고 실제 카메라 ROS 영상 수신도 확인했습니다. Uno 새 펌웨어 업로드·UART 실물 통신·실차 주행은 미완료입니다. 상세는 UART_DEPLOYMENT_REPORT.md를 확인합니다.
- 기본값은 `enabled: false`, `calibrated: false`입니다. 바퀴 반지름·좌우 간격·CPR 실측 전 자율주행 출력은 거부합니다.

공식 참고: [Pi GPIO](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html), [pigpio 하드웨어 PWM API](https://github.com/joan2937/pigpio/blob/master/pigpio.py), [TB6612 데이터시트](https://toshiba.semicon-storage.com/info/TB6612FNG_datasheet_en_20141001.pdf?did=10660&prodName=TB6612FNG).

## UART 통신 변경 — 2026-11-13

Pi와 Uno 통신은 USB 대신 GPIO UART를 사용합니다. 기본 포트는 `/dev/serial0`, 115200 baud, 8N1입니다. 데이터 프로토콜 RA2와 센서 핀은 같습니다.

| 연결 | 배선 |
|---|---|
| Pi TX | GPIO14, 물리 8 → Uno D0 RX |
| Pi RX | GPIO15, 물리 10 ← **5V→3.3V 변환** ← Uno D1 TX |
| 기준 전압 | Pi GND ↔ Uno GND |

**Uno TX 5V를 Pi RX에 직접 연결하지 않습니다.** 레벨 변환기 또는 분압을 사용합니다. 분압 예: Uno D1 → 1kΩ → Pi RX 연결점, 연결점 → 2kΩ → GND (약 3.33V). Pi GPIO14의 3.3V TX는 Uno RX로 입력합니다. Uno는 별도의 적절한 전원이 필요합니다.

Uno D0/D1은 이 UART 전용입니다. USB 프로그래밍 시에는 Pi TX/RX 선을 분리하여 USB-UART와 신호가 충돌하지 않게 합니다. Pi 14/15만 연결하는 것으로 Uno의 USB 자동 리셋/DTR까지 제공되는 것은 아닙니다. 따라서 펌웨어 업로드는 노트북 USB/별도 프로그래머로 하거나, 별도 리셋 배선·부트로더 절차가 필요합니다.

Pi에서는 시리얼 로그인 콘솔을 해제하고, enable_uart=1 및 Pi 4의 disable-bt 오버레이로 PL011을 GPIO14/15에 배정합니다. 적용에는 재부팅이 필요하며 `/dev/serial0`의 실제 대상을 확인합니다. 모터 핀을 점유하던 I2C/SPI/아날로그 오디오는 해제합니다. Bluetooth UART를 재배정하는 설정이므로 Bluetooth는 사용할 수 없고 Wi-Fi는 계속 사용합니다.

앞 표의 D0/D1 USB 통신용 표기 및 USB 데이터 케이블 항목은 이 UART 구성으로 대체합니다. USB는 필요할 때 펌웨어 업로드 용도로만 사용합니다.
