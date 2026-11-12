from pathlib import Path
import json,math,sys,hashlib,zipfile
from collections import Counter
from xml.sax.saxutils import escape
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,KeepTogether,Preformatted
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4

BASE=Path(__file__).resolve().parents[2]
DATA=BASE/'output/picar_validation'
OUT=BASE/'output/pdf/PiCar-B_오프라인검증_결과예측_대응보고서.pdf'
OUT.parent.mkdir(parents=True,exist_ok=True)
R=json.loads((DATA/'results.json').read_text(encoding='utf-8'))
S=json.loads((DATA/'validation_summary.json').read_text(encoding='utf-8'))
C=json.loads((DATA/'compat_results.json').read_text(encoding='utf-8'))
F=json.loads((DATA/'candidate_results.json').read_text(encoding='utf-8'))
TEST={t['id']:t for t in R['tests']}
pdfmetrics.registerFont(TTFont('MG','C:/Windows/Fonts/malgun.ttf'))
pdfmetrics.registerFont(TTFont('MGB','C:/Windows/Fonts/malgunbd.ttf'))
pdfmetrics.registerFont(TTFont('Code','C:/Windows/Fonts/consola.ttf'))
pdfmetrics.registerFontFamily('MG',normal='MG',bold='MGB',italic='MG',boldItalic='MGB')
NAVY=colors.HexColor('#17314B');BLUE=colors.HexColor('#176D9B')
INK=colors.HexColor('#263443');MUTED=colors.HexColor('#617486')
LINE=colors.HexColor('#D9E3EC');PALE=colors.HexColor('#F2F6FA')
GREEN=colors.HexColor('#19735A');RED=colors.HexColor('#A43F43');AMBER=colors.HexColor('#936615')
W,H=A4;WIDTH=W-84
styles={
 'body':ParagraphStyle('body',fontName='MG',fontSize=9.5,leading=15.5,textColor=INK,wordWrap='CJK',spaceAfter=8),
 'small':ParagraphStyle('small',fontName='MG',fontSize=8.2,leading=12.7,textColor=MUTED,wordWrap='CJK',spaceAfter=6),
 'h1':ParagraphStyle('h1',fontName='MGB',fontSize=21,leading=29,textColor=NAVY,wordWrap='CJK',spaceAfter=16),
 'h2':ParagraphStyle('h2',fontName='MGB',fontSize=12.5,leading=18.5,textColor=BLUE,wordWrap='CJK',spaceBefore=8,spaceAfter=8),
 'cell':ParagraphStyle('cell',fontName='MG',fontSize=8.7,leading=13.2,textColor=INK,wordWrap='CJK'),
 'head':ParagraphStyle('head',fontName='MGB',fontSize=8.5,leading=12.5,textColor=colors.white,wordWrap='CJK'),
 'code':ParagraphStyle('code',fontName='Code',fontSize=8.0,leading=12,textColor=INK,backColor=PALE,borderPadding=9,spaceBefore=5,spaceAfter=11),
 'tag':ParagraphStyle('tag',fontName='MGB',fontSize=8.5,leading=13,textColor=BLUE,spaceAfter=8),
 'ledger':ParagraphStyle('ledger',fontName='MG',fontSize=7.7,leading=11.2,textColor=INK,wordWrap='CJK'),
 'mono':ParagraphStyle('mono',fontName='Code',fontSize=7.4,leading=11,textColor=INK,wordWrap='CJK',spaceAfter=5),
}
story=[]
def p(s,style='body'):return Paragraph(s,styles[style])
def add(s,style='body'):story.append(p(s,style))
def h2(s):add(s,'h2')
def code(s):story.append(Preformatted(s,styles['code']))
def gap(n=6):story.append(Spacer(1,n))
def table(headers,rows,widths=None,small=False):
    st='ledger' if small else 'cell'
    dat=[[p(escape(str(x)),'head') for x in headers]]
    dat += [[p(str(x),st) for x in row] for row in rows]
    t=Table(dat,colWidths=widths or [WIDTH/len(headers)]*len(headers),repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([
      ('BACKGROUND',(0,0),(-1,0),NAVY),('VALIGN',(0,0),(-1,-1),'TOP'),
      ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),
      ('TOPPADDING',(0,0),(-1,-1),5 if small else 7),('BOTTOMPADDING',(0,0),(-1,-1),5 if small else 7),
      ('LINEBELOW',(0,0),(-1,0),.7,NAVY),('LINEBELOW',(0,1),(-1,-1),.35,LINE),
      ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,PALE]),
    ]))
    story.append(t);gap(9)
def card(title,text,color=BLUE):
    t=Table([[p(title,'h2')],[p(text)]],colWidths=[WIDTH])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),('BOX',(0,0),(-1,-1),.5,LINE),
      ('LINEBEFORE',(0,0),(0,-1),3,color),('LEFTPADDING',(0,0),(-1,-1),12),
      ('RIGHTPADDING',(0,0),(-1,-1),12),('TOPPADDING',(0,0),(-1,0),0),
      ('BOTTOMPADDING',(0,-1),(-1,-1),3)]))
    story.append(KeepTogether([t,Spacer(1,11)]))
page_num=0
def page(title,tag):
    global page_num
    if story:story.append(PageBreak())
    page_num+=1
    add(tag,'tag');add(title,'h1')

page('PiCar-B 오프라인 검증\n결과 예측 및 대응 보고서'.replace('\n','<br/>'),'ADEEPT PICAR-B MARS ROVER / ADR012 / 2026.10.16')
add('제조사 ZIP 코드와 이전 작업 기록을 바탕으로 수행한 실행 시험, 조건별 예상 결과, 복구 준비 사항을 정리했습니다. 실제 라즈베리파이에는 접속하지 않았습니다.')
stats=[]
for num,label,col in [('136','원본 코드 시험',BLUE),('98','통과',GREEN),('31','문제 재현 기록',RED),('7','동작·환경 관찰',AMBER)]:
    stats.append(Paragraph(f'<font color="{col.hexval()}" size="27"><b>{num}</b></font><br/><font size="8.5">{label}</font>',ParagraphStyle('stat',parent=styles['body'],leading=32)))
t=Table([stats],colWidths=[WIDTH/4]*4)
t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),('LEFTPADDING',(0,0),(-1,-1),12),('TOPPADDING',(0,0),(-1,-1),13),('BOTTOMPADDING',(0,0),(-1,-1),13)]))
story.append(t);gap(14)
card('판단: 소프트웨어 문제는 재현됐고, 실제 주행 불능 원인은 아직 미확정입니다.',
     '일반 조종 명령, HTTP 화면·합성 영상 스트림, 로컬 WebSocket 왕복은 동작했습니다. 반면 HOME, 입력 예외, 연결 종료 후 출력 유지, 특정 거리 값의 반복 처리 등에서 문제가 확인됐습니다. <b>31건은 서로 다른 버그 31개가 아니라, 같은 원인의 여러 입력·상황을 포함한 시험 기록 수</b>입니다.')
h2('가장 먼저 볼 결과')
add('1. <b>Python 3.13.5 + websockets 13.0</b>은 이번 통신 시험을 통과했습니다. OS/Python을 우선 바꿀 근거는 부족합니다.<br/>2. <b>websockets 14.2</b>에서는 원래 시작 방식이 실패했습니다. 실제 설치 버전과 8888 포트 확인이 우선입니다.<br/>3. 연결 종료·예외 뒤 <b>모터 출력 명령이 남는 현상</b>을 재현했습니다. 실기 시험 전에 종료 시 정지 처리와 수동 조종 시간 제한을 준비해야 합니다.')
add('추가로 호환성 프로브 15건, 복사본의 제한된 수정안 시험 14건을 실행했습니다. 수정안 시험은 모두 통과했으며 실제 기기에는 적용하지 않았습니다.','small')
add('원본 ZIP과 이전 PDF는 SHA-256 전후 일치. ZIP 전체 복사본을 만든 다음, 수정 실험은 그 복사본에서 추출한 파일에만 수행했습니다.','small')

page('검증 방법과 원본 보존','01 / 범위와 한계')
table(['구분','실제로 수행한 일','판단 범위'],[
 ['정적 검사','ZIP 내 Python 파일 35개를 3.11 / 3.13 / 3.14 문법으로 검사. 프런트엔드 경로와 코드 연결 확인.','문법·코드 구조 확인. 전체 런타임 호환성 보증은 아님.'],
 ['함수 실행','원래 함수·클래스의 AST를 그대로 추출해 실행. 모터·서보는 실제 Adafruit 드라이버를 사용.','외부 장치 접근을 메모리 I²C로 교체. 전기적·기계적 특성 제외.'],
 ['통신·영상','실제 websockets 로컬 TCP 통신, 원본 Flask 라우트, 실제 OpenCV 합성 영상 처리.','GPIO·실제 카메라 드라이버·라즈베리파이 네트워크는 미검증.'],
 ['장애 주입','잘못된 명령, 연결 종료, I²C/LED 오류, 거리 센서 한계값, 패키지 설치 실패를 주입.','장애가 발생할 때 코드의 반응을 관찰. 현장 발생 빈도는 모름.'],
 ['수정 비교','전체 ZIP 복사본에서 꺼낸 4개 파일에 한정된 수정안을 적용하고 14건 검사.','복사본 시험일 뿐, 모든 오류를 고친 완성본은 아님.'],
 ],[70,243,WIDTH-313])
h2('시험 환경과 이전 기록은 구분했습니다')
add('이번 PC: Windows 11, 기본 Python 3.14.6. 핵심 동적 시험은 별도 가상환경의 <b>Python 3.13.5</b>에서 실행했습니다. 호환성 비교에는 3.11.9와 3.14.6도 사용했습니다. 이전 PDF의 Ubuntu 24.04는 다른 세션에서 기록한 PC 정보이며, 이번 시험 PC의 OS가 아닙니다.')
add('주요 시험 패키지: websockets 13.0, Flask 3.1.3, flask-cors 6.0.5, NumPy 2.5.4, OpenCV 5.0.0, Adafruit Motor 3.5.0, PCA9685 3.4.22. 이 버전들은 이번 PC에 준비한 환경이며 <b>라즈베리파이에 현재 설치된 버전은 미확인</b>입니다. 전체 목록은 requirements-test.txt에 있습니다.','small')
card('원본 보호 방식',
     '원본 ZIP 60,487,206바이트와 이전 PDF 102,749바이트의 해시를 기록했습니다. ZIP 전체를 working_copy에 복사한 뒤 추출본에서만 수정했습니다. 비교 기준 source/의 Python 35개도 ZIP과 바이트 단위 일치를 확인했습니다. 원본 ZIP·이전 PDF·전체 ZIP 복사본 모두 해시가 일치합니다.',GREEN)
add('전체 Debian/ARM OS 부팅, systemd 실동작, 실제 설치 성공, GPIO/I²C 전기 신호, 배선·배터리·모터 토크·충돌·주행 거리는 시험하지 않았습니다. ZIP에는 URDF/SDF/world/STL/OBJ 시뮬레이션 자산이 없어서 차량 물리 시뮬레이션은 구성하지 않았습니다. 전체 분기 커버리지 100%를 측정한 시험도 아닙니다.','small')

page('무엇이 정상 동작했는가','02 / 통과 결과와 집계')
group_names={'static':'문법·구조','motor':'모터 출력','servo':'서보','command':'조종·기능 명령','protocol':'입력·인증','algorithm':'센서 제어 알고리즘','vision':'영상 처리','http':'HTTP·영상 전송','network':'WebSocket·연결','install':'설치·시작','other':'기타 보조 기능','fault':'추가 장애 주입','integrity':'원문 무결성'}
table(['시험군','통과','문제 재현','관찰','합계'],[
 [group_names[k],v.get('PASS',0),v.get('DEFECT',0),v.get('OBSERVATION',0),sum(v.values())]
 for k,v in S['groups'].items()
 ]+[['전체',98,31,7,136]],[WIDTH-220,55,65,50,50])
h2('통과가 의미하는 것')
add('전진·후진·좌우·정지·카메라 방향 명령 12종은 해당 함수까지 전달됐습니다. 기능 명령 13종과 스위치 6종도 목적 함수로 연결됐습니다. 모터 속도 입력 -10~110은 드라이버 계층에서 0~100으로 제한됐고, 정지 명령은 네 모터 객체의 throttle을 모두 0으로 바꿨습니다.')
add('원본 Flask의 첫 화면·JS·CSS는 HTTP 200, 없는 파일은 404를 반환했습니다. 합성 JPEG의 MJPEG 전송 형식도 확인했습니다. 실제 로컬 WebSocket에서 인증 후 속도 설정·전진·조향·정지 명령을 주고 응답을 받았습니다.')
add('<b>해석 주의:</b> throttle 0.2는 드라이버 입력값입니다. 실제 바퀴 RPM이 최대의 20%라는 측정값이 아닙니다. 서보 120° 역시 코드가 계산한 명령각이며 실제 조향 바퀴의 각도를 측정한 값이 아닙니다.','small')

page('먼저 대비해야 할 실행 오류','03 / 우선순위가 높은 재현 결과')
card('A. 연결이 종료돼도 마지막 모터 출력 명령이 남음',
     '<b>재현:</b> 실제 로컬 WebSocket에서 속도 20 → 전진 → 연결 종료. 종료 후 motor1.throttle이 0.2로 남았습니다. 전진 뒤 HOME 예외, LED 오류, 수신 작업 취소에서도 출력 유지가 관찰됐습니다.<br/><b>코드 근거:</b> WebServer.py:329~401의 수신·연결 처리에 종료 시 정지를 보장하는 finally가 없습니다.<br/><b>대비:</b> 조종권을 가진 연결에 한해 종료·오류 시 자동 모드/서보 작업을 해제하고 모터를 정지시키는 경로를 추가합니다. 수동 조종에는 별도 명령 만료 시간을 둡니다. 정지 쓰기 자체가 실패하는 I²C 장애는 소프트웨어만으로 정지를 보장할 수 없습니다.',RED)
card('B. HOME 버튼에서 IndexError',
     '<b>재현:</b> home을 보내면 리스트 인덱스 오류. 전진 뒤 누르면 예외와 함께 기존 출력이 남습니다.<br/><b>원인:</b> WebServer.py:255~258에서 서보 번호 대신 초기 각도 90을 moveServoInit()에 전달합니다. 유효한 서보 번호는 0~7입니다.<br/><b>대비:</b> 원래 수동 명령에 사용한 채널 0/1/2로 복귀시키는 수정안을 복사본에서 검증했습니다. 실제 배선과 각 축의 초기각 설정은 기기에서 확인해야 합니다.',RED)
card('C. 설치 실패가 있어도 완료 안내와 재부팅까지 갈 수 있음',
     '<b>재현:</b> 설치 스크립트 전체를 가짜 OS·프로세스·메모리 파일시스템에서 실행했습니다. apt 27회와 pip 33회가 모두 실패하도록 했어도 완료 안내와 재부팅 요청에 도달했습니다. 실제 시스템 명령 실행은 0건입니다.<br/><b>대비:</b> 재부팅을 설치 성공의 근거로 삼지 않습니다. 모듈 경로·패키지 버전·서비스 로그를 먼저 수집하고, 실패하면 중단하도록 설치 절차를 보완합니다.',RED)
card('D. LED 초기화 오류가 조종 서버 시작을 막는 경로',
     '<b>재현:</b> LED 생성자에 예외를 주입하면 예외 처리에서 아직 만들어지지 않은 WS2812를 다시 참조해 NameError가 발생했습니다(WebServer.py:412~423).<br/><b>예측:</b> 이 블록 앞에서 HTTP 스레드가 시작되므로 영상·화면은 살아 있어도 조종 서버가 시작되지 않을 수 있습니다.<br/><b>대비:</b> 선택 장치의 실패를 별도로 기록하고 None/초기화 상태를 확인한 뒤 정리합니다. SPI 비활성화가 항상 이 예외를 일으킨다고 확인한 것은 아닙니다.',RED)

page('입력 처리와 서보의 추가 문제','04 / 발생 조건과 개선 방향')
table(['조건·시험','관찰한 결과','대비 방법'],[
 ['잘못된 인증 입력\nAUTH-MALFORMED','admin처럼 콜론 없는 문자열은 IndexError. 정상 admin:123456은 통과.','split(":", 1) 결과 개수와 문자열 형식을 먼저 검증. 형식 오류를 응답하고 연결·조종 상태 정리.'],
 ['숫자·JSON 형식 오류\nINPUT-* / JSON-*','SiLeft x, CVFLL1 x, PWMMS NaN 등과 필드 누락/짧은 배열에서 예외.','명령별 인자 수·타입·범위 검증. 잘못된 요청에는 오류 응답. motor 제어 예외에는 정지 경로 연결.'],
 ['64개 입력 변형\nINPUT-FUZZ','정해진 시드로 만든 64개 중 22개가 처리되지 않은 예외. IndexError 5, ValueError 17.','프런트엔드 정상 입력만 가정하지 않고 서버에서도 검증. 22/64는 장애 확률이나 보안 취약도 수치가 아님.'],
 ['과도한 미세조정\nSERVO-CAL','초기 90에서 우측 91회 조정하면 181이 되어 드라이버의 Angle out of range 발생.','각도 상한·하한을 명령 적용 전 제한. 선택 채널의 유효 범위도 함께 검사.'],
 ['서보 자동 보간\nSERVO-AUTO','기본 설정의 대기 시간이 약 -0.0233초가 되어 ValueError. 일반 좌우 조향 경로와는 다름.','음수 대기 시간 방지. 복사본 수정 후 목표 120° 도달 확인. 실제 이동 시간과 부드러움은 실기 재조정.'],
 ['보조 함수\nINFO-01 / CV-MAP / BATTERY-PCT','GPU 온도 함수의 os import 누락. 영상 map 보조 함수 결과 2.5(기대 5). 배터리 표시 -299%~128%.','사용하는 보조 함수부터 import·수식·표시 범위를 수정. 일반 주행 불능의 직접 원인으로 확정하지 않음.'],
 ],[112,194,WIDTH-306])
h2('오류로 단정하지 않고 관찰로 남긴 항목')
add('조향 해제 TS는 전진 상태 변수를 유지하면서 모터를 정지합니다. 여러 클라이언트는 전역 제어 상태를 공유해 다른 연결의 명령을 덮어쓸 수 있습니다. 모르는 명령에도 status=ok를 반환합니다. 요구 동작에 따라 정책을 정해야 하는 항목이며, 이번 집계에서는 별도의 동작 관찰로 분류했습니다.')
add('서보 업데이트 3회에서 MODE1=0 레지스터 쓰기 6회를 기록했습니다. 드라이버 초기화/주파수 설정 과정에서 공유 PWM 칩을 계속 재설정하는 구조입니다. 떨림이나 동시 접근 충돌은 실제로 측정하지 않았습니다. I²C/PCA9685 객체를 공유하고 잠금으로 제어하는 방향을 검토할 수 있습니다.','small')

page('센서와 합성 영상 시뮬레이션','05 / 알고리즘 실행 결과')
card('거리 200cm에서 반복 처리가 끝나지 않음',
     'functions.py:210~219는 >200일 때 누적하고, 다른 분기에서 &lt;200일 때 종료합니다. 정확히 200은 종료 조건에 들어가지 않습니다. 200을 고정 입력했을 때 10,001회 읽기에서 시험을 강제 중단했습니다. 201과 NaN의 장애 입력도 1,001회 읽기까지 종료되지 않았습니다.<br/><b>예측:</b> 동일 값이 지속되면 해당 자동 동작이 멈춘 듯 보이거나 마지막 출력이 유지될 수 있습니다. 센서 최대 설정은 2m이지만 실제로 200이 얼마나 자주 반환되는지는 확인하지 않았습니다.<br/><b>대비:</b> 재시도 상한, 유효 범위, 센서 오류 시 정지 정책을 둡니다. 복사본에서는 정상 200을 반환하고 무효 값은 6회 후 정지·오류로 처리하도록 시험했습니다.',RED)
table(['시험','실행한 입력','관찰 결과'],[
 ['라인 센서','3비트 조합 000~111 총 8개','원래 분기표대로 출력. 다만 초기 last_status=0에서 첫 000 입력은 생략되어 구동 명령이 나오지 않음.'],
 ['거리 유지','20 / 30 / 35 / 40 / 50cm','각각 -0.4 / 0 / 0 / 0 / +0.4 출력. 30~40cm 정지 구간 확인.'],
 ['장애물 회피','먼 거리, 가까운 거리, 좌측 여유, 우측 여유','전진·후진·좌·우 분기 실행. 차량이 실제 장애물을 피하는지는 미검증.'],
 ['빛 추적','ADC 80 / 127 / 180','좌측·중앙·우측 분기 실행. 실제 광센서 감도·극성은 미검증.'],
 ['흰 선 영상','640×480, 선 위치 x=100 / 320 / 540','검출 중심 99 / 319 / 539. 위치 오차 1픽셀. 빈 영상은 선 없음과 정지 처리 확인.'],
 ['노란 표적','중심 (450,200), 반지름 40픽셀','실제 OpenCV가 중심 (450,200), 반지름 40.0 검출. 빈 영상은 표적 없음.'],
 ['영상 행 범위','높이 480인 영상에 스캔 행 999','IndexError. 행 위치는 영상 크기 범위 내에서 검증 필요.'],
 ],[80,172,WIDTH-252])
add('합성 영상은 단색·고대비 조건입니다. 조명, 반사, 흔들림, 렌즈 왜곡, 실제 카메라 색 공간, 프레임 지연을 반영하지 않았습니다. 실제 선 추적 성공률이나 색 추적 성능을 예측할 수치는 산출하지 않았습니다.','small')

page('Python·통신 라이브러리 호환성','06 / 15개 독립 프로브')
add('각 조합을 새 Python 프로세스에서 실행했습니다. 원래 서버 시작 순서와 원래 연결 함수의 인자를 사용하되, 네트워크는 127.0.0.1의 임시 포트로 제한하고 장치 처리 본문은 대체했습니다. 따라서 이 표는 API 호환성 시험이며 전체 로봇 서버 부팅 시험은 아닙니다.')
table(['Python / websockets','원래 시작 방식','루프만 조정','루프+함수 인자 조정'],[
 ['3.11.9 / 13.0','통과','통과','통과'],
 ['3.13.5 / 13.0','통과','통과','통과'],
 ['3.13.5 / 14.2','실패: 실행 중 루프 없음','실패: path 인자 누락','통과'],
 ['3.14.6 / 13.0','실패: 현재 루프 없음','통과','통과'],
 ['3.14.6 / 14.2','실패: 실행 중 루프 없음','실패: path 인자 누락','통과'],
 ],[123,130,120,WIDTH-373])
h2('왜 이런 결과가 나왔는가')
add('원래 WebServer.py:429~430은 동기 코드에서 websockets.serve()를 먼저 만들고 get_event_loop()로 실행합니다. websockets 14부터 최상위 serve의 구현이 바뀌며 이 시작 방식이 충돌합니다. 실행 중인 루프 안으로 옮기기만 하면, 이번에는 main_logic(websocket, path)의 필수 path 인자가 없어 연결 처리에 TypeError가 발생했습니다. 클라이언트에서는 1011 오류로 보였습니다. [웹 자료 1, 2]')
add('Python 3.14에서는 현재 이벤트 루프가 없을 때 get_event_loop()가 RuntimeError를 발생시키는 변경도 있습니다. 이번 3.14.6 + websockets 13.0 프로브에서 이를 재현했습니다. 3.13.5 + 13.0은 통과했으므로 이 오류를 기존 라즈베리파이의 확정 원인으로 옮겨 적으면 안 됩니다. [웹 자료 3]')
card('현재 기기에 대한 우선 판단',
     '제조사 setup.py는 websockets==13.0을 지정합니다. 실제 서비스가 사용하는 Python에 13.0이 설치돼 있고 나머지 초기화가 성공한다면, 이번 결과상 통신 API 자체는 동작할 가능성이 있습니다. 다른 버전이 설치돼 있다면 해당 오류와 로그를 먼저 대조하십시오. 제조사 ZIP의 시작 설명서에도 Trixie 안내가 있어, Debian 13이라는 이름만으로 부적합하다고 단정할 수 없습니다.',GREEN)
add('조정 프로브는 asyncio.run()으로 루프를 시작하고 연결 함수의 path를 선택 인자로 바꾼 경우입니다. 5개 조합 모두 통과했지만 해당 프로브는 실제 장치 초기화·전체 기능을 검증하지 않았으며, 작업 복사본 WebServer.py에 이 변경을 일괄 적용한 것은 아닙니다.','small')

page('실제 기기에서 나올 수 있는 결과','07 / 조건부 예측과 대비')
add('아래 예측은 시험 증거에 따른 조건부 판단입니다. 발생 확률은 계산하지 않았습니다. <b>높음</b>은 같은 코드·입력이라면 재현 근거가 강하다는 뜻이며, 그 상황이 현재 기기에 이미 존재한다는 뜻은 아닙니다.')
table(['조건','예상되는 증상·결과','근거·확신','대비'],[
 ['서비스의 websockets가 14.2이고 원래 시작 코드를 사용','영상·화면은 열려도 8888 조종 서버가 준비되지 않거나 연결이 1011로 종료될 수 있음.','API 충돌은 재현. 실제 설치 버전 미확인. 조건 일치 시 높음.','서비스 Python 경로·버전, 5000/8888 포트, journal의 루프/path 오류 확인.'],
 ['Python 3.13.5 + websockets 13.0, 장치 초기화 정상','기본 조종 명령이 하위 제어 함수까지 전달될 가능성. 여전히 실제 모터 동작은 미확인.','로컬 왕복 통과. Pi 전체 정상 동작 판단은 중간.','통신이 되면 I²C·모터 포트·서보 채널·전원 경로 순으로 분리 점검.'],
 ['동일 원문에서 HOME 입력','IndexError로 해당 연결 처리 중단. 움직이던 출력이 남을 수 있음.','함수 실행과 전진 후 입력에서 재현. 높음.','복사본의 채널 인자 수정과 종료 정지 처리.'],
 ['전진 중 연결 종료 또는 처리 예외','마지막 PWM/모터 명령이 남을 수 있음. 실제 차의 거동은 부하·드라이버·전원에 좌우됨.','가짜 I²C 출력 유지 재현. 물리적 결과는 미측정.','조종 연결 소유권, 종료 시 정지, 수동 명령 만료 시간. 초기 실기는 바퀴를 띄워 짧게 실시.'],
 ['자동 모드에서 거리 200이 지속','거리 보정 반복이 끝나지 않아 모드가 멈춘 듯 보임.','고정 값 주입에서 재현. 실제 센서 발생 빈도 모름.','유효 값/오류 분리와 읽기 횟수·시간 상한.'],
 ['I²C 장치 0x5f에 접근 실패','드라이버 초기화 또는 제어 명령 실패. 카메라 정상 여부만으로 배제 불가.','장애 주입에서 ValueError 재현. 현재 하드웨어 상태 미확인.','먼저 로그에서 정확한 실패 지점 확인. I²C 활성화·장치 경로·HAT 전원 점검.'],
 ['설치는 재부팅됐지만 패키지 일부 실패','ModuleNotFoundError, 서비스 실패, 일부 기능 비활성화 가능.','설치 실패 후 완료·재부팅 경로 재현. 실제 설치 성공 미확인.','로그·패키지 위치 수집 후 실패한 항목만 해결. 설치 스크립트 반복 실행은 후순위.'],
 ],[96,167,112,WIDTH-375])
add('영상이 보인다는 사실은 일부 초기화가 진행됐다는 단서입니다. 그러나 현재 Pi의 코드가 이 ZIP과 같은지, 같은 프로세스의 영상인지 아직 확인하지 않았습니다. 이 때문에 특정 하드웨어 고장이나 특정 라이브러리를 원인으로 확정하지 않았습니다.','small')

page('라즈베리파이에서 이어갈 점검 순서','08 / 먼저 자료를 모으고 원인을 좁히기')
h2('1. 서비스가 실제로 무엇을 실행하는지 확인')
code('sudo systemctl status Adeept_Robot.service --no-pager -l\nsudo systemctl cat Adeept_Robot.service\nsudo journalctl -u Adeept_Robot.service -b --no-pager -n 150\nss -ltnp')
add('5000은 화면·영상, 8888은 조종 통신입니다. 5000만 열려 있으면 두 번째 서버 시작 단계와 그 앞의 LED 초기화 로그부터 확인합니다. 서비스가 active여도 조종 기능까지 정상이라는 뜻은 아닙니다.')
h2('2. 서비스의 Python과 같은 환경에서 패키지 확인')
code('python3 --version\npython3 -c "import sys; print(sys.executable)"\npython3 -c "import importlib.metadata as m; print(m.version(\'websockets\'))"\nlocale\nlocale -a')
add('서비스의 ExecStart/startup.sh가 다른 Python을 실행하면 그 경로로 확인해야 합니다. 사용자 Python에서 확인한 버전을 root 서비스 환경에 그대로 적용해 해석하지 않습니다. 로케일 경고는 실제 문자열 처리 문제를 함께 확인하되, 현재 자료만으로 모터 미작동의 직접 원인이라고 볼 근거는 없습니다.','small')
h2('3. 제공한 수집 스크립트 활용')
code('bash collect_picar_diagnostics.sh')
add('스크립트는 Pi에서 실행하는 용도입니다. 현재 디렉터리에 날짜가 붙은 diagnostics.txt를 만들고 OS·서비스·최근 로그·포트·패키지 메타데이터·장치 경로·소스 해시를 모읍니다. 설치, 서비스 변경, 재부팅, 모터 명령은 없습니다. PC에서는 bash -n 문법 검사만 완료했으며 실제 Pi 실행 결과는 아직 없습니다.')
card('점검 후 분기',
     '<b>루프/path 오류:</b> 버전과 시작 코드 대응 → <b>모듈 누락:</b> 서비스 환경의 패키지 경로 확인 → <b>I²C 오류:</b> 인터페이스·HAT 접근 확인 → <b>통신 정상·출력 무반응:</b> 실제 배선과 전원, 모터 M1 및 서보 0/1/2를 하나씩 검증 → <b>특정 버튼만 실패:</b> 해당 명령과 이번 재현 로그를 대조합니다.')

page('수정·재시험·복귀 대비 방법','09 / 원본을 유지하는 실기 준비')
table(['단계','예상 결과','문제가 남으면'],[
 ['자료 수집','실제 서비스 실행 경로, 버전, 포트와 마지막 오류가 드러남.','로그 접근 권한을 확인하고 동일 journal/status 명령만 sudo로 수집.'],
 ['통신 오류 수정','13.0 환경 유지 또는 버전에 맞는 시작 코드 조정 후 8888 접속과 명령 응답 회복 기대.','하드웨어 초기화 예외가 먼저 있는지 확인. 버전만으로 원인을 확정하지 않음.'],
 ['종료 정지 처리 준비','연결 종료·예외·수동 명령 만료 뒤 출력 0을 기대.','자동 모드/서보 스레드가 다시 출력을 쓰는지 확인. 조종권이 없는 연결 종료가 다른 사용자의 동작을 중단하지 않도록 정책 설계.'],
 ['복사본의 최소 수정 적용','HOME의 인덱스 오류, 음수 sleep, 거리 200의 무한 반복 감소 기대.','실제 설치 소스의 해시·행 내용이 동일한지 비교. 배선·초기각과 맞지 않는 채널 변경은 재검토.'],
 ['기능별 짧은 시험','전진/후진·조향·복귀·정지·연결 종료를 각각 확인.','실기 최초에는 바퀴를 띄우고 낮은 출력·짧은 시간으로 확인. I²C 정지 쓰기가 실패하면 전원 차단 수단으로 대응.'],
 ],[100,189,WIDTH-289])
h2('원본 폴더를 건드리지 않는 운영 방법')
add('이번 PC에는 이미 제조사 ZIP 전체 복사본을 만들었습니다. 실제 Pi에서 수정 시험을 이어갈 때도 새 작업 폴더를 따로 만들어 사용합니다. 기존 서비스가 실행 중이면 먼저 그 서비스만 중지해 카메라·포트·장치를 중복 점유하지 않도록 하고, 새 작업 폴더의 코드를 전면 실행해 로그를 확인합니다. 이번 작업에서는 이 실기 조치를 실행하지 않았습니다.')
code('# Raspberry Pi: future manual procedure, not executed here\nsudo systemctl stop Adeept_Robot.service\n# Run only the inspected working-copy server in foreground.\n# End that process and confirm its ports/resources are released.\nsudo systemctl start Adeept_Robot.service')
add('복귀는 시험 프로세스를 종료하고 기존 서비스를 다시 시작하는 순서입니다. 기존 서비스 파일과 원본 코드의 경로를 보존하면 돌아갈 기준이 남습니다. 시험 폴더에서 setup.py를 다시 실행하면 서비스·Wi-Fi 설정까지 바뀔 수 있으므로 이번에 검증한 일부 코드 수정과 설치 작업을 혼동하지 않아야 합니다.','small')
add('제조사 설명서에는 I²C·SPI를 먼저 켜는 절차와 모터·서보 구동 시 전원 공급에 관한 안내가 있습니다. USB에서 카메라가 동작했다고 구동부 전원까지 충분하다고 결론내릴 수 없습니다. 실제 공급 방식은 기기의 배터리·HAT 상태와 함께 확인해야 합니다. [제조사 자료 2, pp.20~22, 31]','small')

page('복사본에서 시험한 수정안','10 / 개선 확인과 남은 과제')
table(['변경한 파일·부분','복사본에서 한 변경','확인한 결과'],[
 ['web/WebServer.py\nHOME','각도 값 대신 수동 명령과 같은 채널 번호 1/2/0을 전달.','초기각을 80/100/110으로 달리한 시험에서도 각 축이 해당 초기값으로 복귀.'],
 ['web/RPIservo.py\nmoveAuto','대기 시간을 max(0.0, 계산값)으로 제한.','음수 대기 예외 없이 목표 120°까지 계산 완료. 실제 이동 시간은 미검증.'],
 ['web/functions.py\ndistRedress','거리 읽기를 6회로 제한. 0~200 정상 값 반환, 무효 값 지속 시 정지 요청 후 오류.','200 정상 반환. 201/NaN/None은 6회 후 정지·오류. 실제 센서 정책은 조정 필요.'],
 ['web/base_camera.py\nCameraEvent','isSet()를 is_set()으로 바꾸는 예방적 정리.','이벤트 설정 통과. 원본 메서드도 이번 환경에서는 통과했으며 재현 오류 수정으로 세지 않음.'],
 ],[119,196,WIDTH-315])
h2('수정안 시험 14건 모두 통과')
add('HOME 1건, 자동 보간 1건, 거리 입력 7건, 카메라 이벤트 1건, 변경 파일 문법 검사 4건입니다. 상세 기록은 candidate_results.json, 변경 비교는 candidate_fixes.patch에 있습니다. 수정 대상은 working_copy/code/ 안의 네 파일뿐이며, 원본 ZIP·원본 PDF·전체 ZIP 복사본은 변경되지 않았습니다.')
card('이 수정본에 아직 포함되지 않은 사항',
     '연결 종료 시 정지 보장, 수동 조종 명령 만료 시간, 다중 연결의 조종권, 입력 형식/범위 전체 검증, LED 초기화 실패 처리, 공유 I²C 접근 정리, 설치 스크립트 실패 중단은 아직 이 네 파일의 수정 범위로 해결하지 않았습니다. 이 복사본을 “모든 문제가 해결된 배포본”으로 사용하면 안 됩니다.',RED)
h2('적용 후 기대와 한계')
add('같은 원문·조건에서 HOME/음수 sleep/거리 한계값 관련 예외는 줄어들 것으로 예상됩니다. 하지만 이 수정만으로 현재의 “영상은 보이지만 주행·조향이 안 됨”이 해결된다고 예측할 수는 없습니다. 실제 로그에 나타난 원인을 먼저 고르고, 수정 후 해당 증상과 회귀 항목을 다시 확인해야 합니다.')
add('통신 API의 조정은 별도 15개 프로브에서 실험했으며, 루프와 함수 인자를 함께 바꾸면 5개 환경 조합 모두 통과했습니다. 이 결과는 교체 방향의 근거이며 후보 코드 전체의 호환성 인증은 아닙니다.','small')

page('근거 자료와 재현 파일','11 / 무결성·출처')
h2('원본 SHA-256 전후 일치')
for row,label in zip(S['integrity'],['제조사 ZIP 원본','이전 진행사항 PDF 원본','제조사 ZIP 전체 복사본']):
    add('<b>'+label+'</b> / '+format(row['size'],',')+' bytes / 변경 없음','small')
    add(escape(row['after']),'mono')
h2('로컬 근거')
add('<b>자료 1.</b> picar 진행사항 정리.pdf, 2쪽. 이전 환경·설치 실행·미확인 사항의 인수인계 기록. 실제 설치 성공과 재부팅 후 동작은 확인되지 않은 것으로 취급했습니다.','small')
add('<b>자료 2.</b> ADR012-V5.1_PiCar-B_MarsRover_SmartCarKit_for_RPi-20260407.zip. Code/adeept_picar-b2/의 Python 35개 및 웹 정적 파일. 주요 원문 행 번호는 ZIP 추출 기준입니다.','small')
add('<b>자료 3.</b> ZIP의 2 Basic Course/Lesson 3 Getting Started with Raspberry Pi.pdf: I²C·SPI 준비 pp.20~22, Trixie 관련 Q&amp;A p.29, 전원 안내 p.31. HAT V3.3 소개 pp.2~3과 서보 미세조정 설명 p.2도 확인했습니다. 문서 인용은 내부 인쇄 페이지 기준입니다.','small')
h2('공식 웹 자료 / 2026.10.16 확인')
links=[
 ('1. websockets 14.0 변경 내역','https://websockets.readthedocs.io/en/14.0/project/changelog.html','최상위 API 구현 변경, 연결 함수 path 인자 변경의 근거.'),
 ('2. websockets asyncio 전환 안내','https://websockets.readthedocs.io/en/14.1/howto/upgrade.html','새 구현으로의 이행 시 연결 함수와 import/API를 함께 조정.'),
 ('3. Python 3.14 이벤트 루프 문서','https://docs.python.org/3.14/library/asyncio-eventloop.html','현재 루프가 없을 때 get_event_loop() 동작 변경.'),
 ('4. Adafruit PCA9685 공식 소스','https://github.com/adafruit/Adafruit_CircuitPython_PCA9685/blob/main/adafruit_pca9685.py','객체 초기화와 레지스터 설정 구조 참고. 실행 시험은 로컬 설치 버전 3.4.22 사용.'),
]
for title,url,note in links:
    add(f'<link href="{url}" color="#176D9B">{title}</link> - {note}','small')
h2('재현 자료 위치')
add('현재 작업 폴더의 <b>output/picar_validation/</b>에 실행 스크립트, results.json, compat_results.json, candidate_results.json, validation_summary.json, requirements-test.txt, candidate_fixes.patch와 README_ko.md를 보관했습니다. collect_picar_diagnostics.sh는 다음 Pi 점검을 위한 자료 수집 도구입니다.','small')
add('다음 부록은 원본 시험 136건의 전체 목록입니다. 각 행의 원래 관찰값·예외 문자열·경고와 상세 입력은 동일 ID의 results.json 항목에서 확인할 수 있습니다. 호환성 15건과 수정안 14건의 개별 목록도 함께 수록했습니다.','small')

# Full original-test ledger, page-sized batches. All rows are represented once.
def brief(t):
    d=t['detail'];i=t['id']
    if 'error' in d:return escape(str(d['error']))
    if 'command' in d:return '명령 '+escape(str(d['command']))
    if 'sensor_bits' in d:return '센서 '+d['sensor_bits']+' / 출력 '+str(d.get('motor1'))
    if 'distance_cm' in d:return '거리 '+str(d['distance_cm'])+'cm'
    if 'speed' in d:return '속도 '+str(d['speed'])+' / 방향 '+str(d['direction'])+' / 출력 '+str(d['throttle'])
    if 'relative_angle' in d:return '입력 '+str(d['relative_angle'])+' / 제한각 '+str(d['clamped_absolute'])
    if i=='INPUT-FUZZ':return '64개 입력 중 예외 22개'
    if i=='SETUP-FULL':return '설치 실패 60회 후 재부팅 요청'
    if 'white_line_x' in d:return '선 '+str(d['white_line_x'])+' / 검출 '+str(d['detected_center'])
    if 'http' in d:return 'HTTP '+str(d['http'])+' / '+str(d.get('bytes',d.get('first_chunk_bytes',''))) +' bytes'
    if 'throttle_after_close' in d:return '연결 종료 후 출력 '+str(d['throttle_after_close'])
    if 'quiet_connection_observation_ms' in d:return '수신 대기·작업 취소 뒤 출력 유지'
    if 'files' in d:return str(d['files'])+'개 파일 / 문법 '+d['grammar']
    if 'percentages' in d:return '표시 범위 -299% ~ 128%'
    if i=='SERVO-BUS':return '서보 3회, MODE1=0 쓰기 6회'
    if i=='VOICE-PATH':return '/home/pi 고정 경로·외부 음성 자산'
    if i=='WS-MULTI':return 'A 전진 후 B 정지로 공유 상태 변경'
    if i=='CMD-RELEASE':return 'TS 후 모터 0, 전진 상태 변수 유지'
    if i=='INPUT-ACK':return '미등록 명령에도 status=ok'
    if i=='SERVO-MAP':return '조향 채널 0 / 초기화 채널 2'
    if i=='LINE-INITIAL':return '첫 000 입력 생략'
    if 'adc' in d:return 'ADC '+str(d['adc'])
    if 'actual' in d:return '계산 '+str(d['actual'])+' / 기대 '+str(d['expected'])
    if i=='INTEGRITY-SOURCE':return '원본 Python 35개 바이트 일치'
    return '상세 값: results.json의 동일 ID 참조'

labels={'PASS':'통과','DEFECT':'문제 재현','OBSERVATION':'관찰'}
title_ko={
 'static':'문법·구조','motor':'모터','servo':'서보','command':'명령','protocol':'입력·인증',
 'algorithm':'센서 알고리즘','vision':'영상','http':'HTTP','network':'연결','install':'설치·시작',
 'other':'보조 기능','fault':'장애 주입','integrity':'무결성'}
batch=24
for start in range(0,len(R['tests']),batch):
    part=R['tests'][start:start+batch]
    page(f'원본 코드 시험 목록 {start+1}~{start+len(part)}','부록 A / 전체 136건 / 중복 입력 조건 포함')
    rows=[]
    for t in part:
        status=labels[t['status']]
        col={'PASS':GREEN,'DEFECT':RED,'OBSERVATION':AMBER}[t['status']].hexval()
        rows.append([escape(t['id']),title_ko[t['group']],f'<font color="{col}">{status}</font>',brief(t)])
    table(['시험 ID','분류','결과','입력·핵심 관찰'],rows,[136,70,58,WIDTH-264],small=True)

page('호환성·수정안 개별 시험 목록','부록 B / 추가 29건')
table(['환경','원래 시작','루프 조정','루프+인자 조정'],[
 [label]+[('통과' if next(t for t in C if t['label']==label and t['mode']==mode)['status']=='PASS' else '비호환') for mode in ['original','running_loop','adapted']]
 for label in dict.fromkeys(t['label'] for t in C)
 ],[179,90,90,WIDTH-359])
add('위 표의 셀 15개가 각각 독립 프로세스의 프로브입니다. 통과 10건, 의도한 비호환 재현 5건. 서버 내부 path 오류와 프로세스 오류 문자열은 compat_results.json에 있습니다.','small')
table(['수정안 시험 ID','결과','확인 내용'],[
 [escape(t['id']),'통과',
  'HOME 축별 초기값 복귀' if t['id']=='FIX-HOME' else
  '목표각 도달·음수 대기 방지' if t['id']=='FIX-AUTO' else
  '거리 값 처리·무효 값 반복 상한' if t['id'].startswith('FIX-DIST') else
  '카메라 프레임 이벤트 설정' if t['id']=='FIX-EVENT' else '변경 파일 문법 검사']
 for t in F['tests']
 ],[247,55,WIDTH-302],small=True)
add('후보 수정 14건 모두 통과. 네 파일의 한정된 수정에 대한 결과이며, 실제 기기의 주행 성공이나 전체 기능 복구를 뜻하지 않습니다.','small')

def draw_page(c,doc):
    c.saveState()
    c.setStrokeColor(LINE);c.setLineWidth(.6);c.line(42,H-37,W-42,H-37)
    c.setFont('MGB',8);c.setFillColor(NAVY);c.drawString(42,H-26,'PiCar-B / 오프라인 검증 보고서')
    c.setFont('MG',7.5);c.setFillColor(MUTED);c.drawRightString(W-42,H-26,'2026.10.16')
    c.setStrokeColor(LINE);c.line(42,38,W-42,38)
    c.setFont('MG',7.2);c.drawString(42,25,'원본 보존 확인 · 물리 하드웨어 미접속 · 조건부 예측')
    c.setFont('MGB',8);c.drawRightString(W-42,25,f'{doc.page:02d}')
    c.restoreState()

doc=SimpleDocTemplate(str(OUT),pagesize=A4,rightMargin=42,leftMargin=42,
    topMargin=55,bottomMargin=51,title='PiCar-B 오프라인 검증 결과 예측 및 대응 보고서',
    author='Codex',subject='원본 보존, 실행 시험, 조건부 예측, 대응 방법')
doc.build(story,onFirstPage=draw_page,onLaterPages=draw_page)
print(OUT)
