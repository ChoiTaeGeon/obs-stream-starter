#!/bin/bash
# ==============================================================================
# [OBS 24시간 방송 자동 재시작 스크립트 (macOS Intel/Apple Silicon 겸용)]
# Finder에서 이 파일(start_obs_restarter.command)을 더블클릭하여 실행하십시오.
# ==============================================================================

# ==============================================================================
# [★ 사용자 설정 영역 - 원하는 값으로 수정하세요]
# ==============================================================================
# 1. 재시작 주기 (시간 단위, 소수점 가능 e.g. 10 = 10시간, 0.5 = 30분, 0.016 = 약 1분)
RESTART_INTERVAL_HOURS=10

# 2. 재시작 방식 선택:
#    - "stream" : OBS 프로그램은 그대로 켜두고 방송 송출(스트림)만 중단 후 재시작 (권장 / OBS WebSocket 사용)
#    - "app"    : OBS 프로그램 자체를 종료 후 재실행하고 방송 자동 시작 (OBS 앱 메모리 누수 방지용)
MODE="stream"

# 3. 방송 중단 후 재시작 전 대기 시간 (초 단위, 버퍼 정리용 권장 5~15초)
COOLDOWN_SECONDS=10

# 4. OBS WebSocket 연결 설정 (MODE="stream" 일 때만 사용)
#    OBS 메뉴 -> 도구(Tools) -> WebSocket 서버 설정(WebSocket Server Settings)에서 확인
OBS_WS_HOST="localhost"
OBS_WS_PORT=4455
OBS_WS_PASSWORD="" # WebSocket 비밀번호가 설정되어 있다면 따옴표 안에 입력하세요. 없으면 빈칸 유지.
# ==============================================================================

# 스크립트가 위치한 폴더로 이동 (더블클릭 실행 시 필수)
cd "$(dirname "$0")"

# 터미널 창 타이틀 설정
echo -ne "\033]0;OBS 자동 재시작 매니저 (주기: ${RESTART_INTERVAL_HOURS}시간)\007"

# 종료 시그널 처리
trap 'echo -e "\n\n[프로그램 종료] 사용자에 의해 자동 재시작 루프가 중단되었습니다."; exit 0' SIGINT SIGTERM

clear
echo "============================================================"
echo "        OBS 24시간 방송 자동 재시작 프로그램 (macOS)        "
echo "============================================================"
echo " - 재시작 주기: ${RESTART_INTERVAL_HOURS} 시간"
echo " - 동작 모드  : $( [ "$MODE" = "stream" ] && echo "송출만 재시작 (WebSocket)" || echo "OBS 앱 전체 재시작" )"
echo " - 재시작 대기: ${COOLDOWN_SECONDS} 초"
echo "============================================================"
echo ""

# 초 단위 주기 계산 (Python을 이용해 소수점 계산 지원)
INTERVAL_SECONDS=$(python3 -c "print(int(float('${RESTART_INTERVAL_HOURS}') * 3600))" 2>/dev/null)
if [ -z "$INTERVAL_SECONDS" ] || [ "$INTERVAL_SECONDS" -le 0 ]; then
    echo "[오류] 올바르지 않은 시간 설정입니다: ${RESTART_INTERVAL_HOURS}"
    echo "아무 키나 누르면 창이 닫힙니다..."
    read -n 1
    exit 1
fi

# -------------------------------------------------------------
# MODE="stream" 환경 준비 (Python 가상환경 및 라이브러리 자동 점검)
# -------------------------------------------------------------
if [ "$MODE" = "stream" ]; then
    if ! command -v python3 &>/dev/null; then
        echo "[오류] python3 명령을 찾을 수 없습니다. 맥에 Python 3를 설치해주세요."
        echo "아무 키나 누르면 창이 닫힙니다..."
        read -n 1
        exit 1
    fi

    # 로컬 가상환경(.venv) 확인 및 생성
    if [ ! -d ".venv" ]; then
        echo "[초기 설정] Python 가상환경(.venv)을 생성합니다..."
        python3 -m venv .venv
    fi

    # 가상환경 Python 사용
    PY_BIN="./.venv/bin/python3"
    PIP_BIN="./.venv/bin/pip"

    # obsws-python 설치 확인
    if ! "$PY_BIN" -c "import obsws_python" 2>/dev/null; then
        echo "[초기 설정] OBS WebSocket 제어 패키지(obsws-python)를 설치합니다..."
        "$PIP_BIN" install --quiet obsws-python
    fi

    echo "[연결 확인] OBS WebSocket 연결 테스트 중..."
    "$PY_BIN" obs_restarter.py --host "$OBS_WS_HOST" --port "$OBS_WS_PORT" --password "$OBS_WS_PASSWORD" --action status
    if [ $? -ne 0 ]; then
        echo ""
        echo "------------------------------------------------------------"
        echo "[주의] OBS WebSocket 연결에 실패했습니다."
        echo "1. OBS Studio가 켜져 있는지 확인하세요."
        echo "2. OBS 상단 메뉴 '도구' -> 'WebSocket 서버 설정'에서"
        echo "   'WebSocket 서버 활성화'가 체크되어 있는지 확인하세요."
        echo "3. 포트(기본 4455)와 비밀번호가 스크립트 설정과 일치하는지 확인하세요."
        echo "------------------------------------------------------------"
        echo "그래도 루프를 계속 실행하시겠습니까? (5초 후 자동으로 계속 진행됩니다)"
        sleep 5
    fi
fi

# -------------------------------------------------------------
# 메인 루프 실행
# -------------------------------------------------------------
CYCLE_COUNT=0

while true; do
    CYCLE_COUNT=$((CYCLE_COUNT + 1))
    
    # 다음 재시작 시각 계산
    TARGET_TIMESTAMP=$(python3 -c "import time; print(int(time.time() + $INTERVAL_SECONDS))")
    NEXT_DATE=$(python3 -c "import datetime; print(datetime.datetime.fromtimestamp($TARGET_TIMESTAMP).strftime('%Y-%m-%d %H:%M:%S'))")
    
    echo ""
    echo "============================================================"
    echo " [사이클 #$CYCLE_COUNT] 방송 모니터링 중..."
    echo " - 현재 시각        : $(date '+%Y-%m-%d %H:%M:%S')"
    echo " - 다음 재시작 예정 : $NEXT_DATE (약 ${RESTART_INTERVAL_HOURS}시간 후)"
    echo "============================================================"
    echo " (중단하려면 이 터미널 창에서 Ctrl + C 를 누르세요)"
    echo ""

    # 실시간 카운트다운 루프
    while true; do
        CURRENT_TS=$(python3 -c "import time; print(int(time.time()))")
        REMAINING=$((TARGET_TIMESTAMP - CURRENT_TS))
        
        if [ "$REMAINING" -le 0 ]; then
            break
        fi

        # 시:분:초 변환
        HOURS=$((REMAINING / 3600))
        MINS=$(((REMAINING % 3600) / 60))
        SECS=$((REMAINING % 60))

        printf "\r >> 다음 방송 재시작까지 남은 시간: %02d시간 %02d분 %02d초 " "$HOURS" "$MINS" "$SECS"
        
        # 1초 대기
        sleep 1
    done

    echo ""
    echo ""
    echo "============================================================"
    echo " [방송 재시작 시각 도달] 방송 재시작 절차를 시작합니다."
    echo " 시각: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "============================================================"

    # 재시작 모드에 따른 동작
    if [ "$MODE" = "stream" ]; then
        "$PY_BIN" obs_restarter.py \
            --host "$OBS_WS_HOST" \
            --port "$OBS_WS_PORT" \
            --password "$OBS_WS_PASSWORD" \
            --cooldown "$COOLDOWN_SECONDS" \
            --action restart
    elif [ "$MODE" = "app" ]; then
        echo "[1/3] OBS 프로그램 종료 중..."
        osascript -e 'quit app "OBS"' 2>/dev/null || killall "OBS" 2>/dev/null
        
        echo "[2/3] $COOLDOWN_SECONDS 초간 대기합니다..."
        sleep "$COOLDOWN_SECONDS"

        echo "[3/3] OBS 프로그램 재실행 및 방송 시작 요청..."
        open -a "OBS" --args --startstreaming
        echo ">>> [완료] OBS 재실행 완료 <<<"
    fi

    echo "============================================================"
    echo " [사이클 #$CYCLE_COUNT 완료] 다음 주기를 준비합니다."
    echo "============================================================"
    sleep 3
done
