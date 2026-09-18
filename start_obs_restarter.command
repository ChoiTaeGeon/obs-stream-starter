#!/bin/bash
# ==============================================================================
# [OBS 24시간 방송 자동 재시작 스크립트 (macOS Intel/Apple Silicon 겸용)]
# Finder에서 이 파일(start_obs_restarter.command)을 더블클릭하여 실행하십시오.
# ==============================================================================

# ==============================================================================
# [★ 사용자 설정 영역 - 원하는 값으로 수정하세요]
# ==============================================================================
# 1. 방송(Stream) 자동 재시작 설정
ENABLE_STREAM_RESTART=true      # 방송 자동 재시작 사용 (true / false)
STREAM_INTERVAL_HOURS=10        # 방송 재시작 주기 (시간 단위, 소수점 가능 e.g. 10 = 10시간, 0.5 = 30분)

# 2. 동영상 녹화(Recording) 자동 재시작 설정 [2시간 단위 설정]
ENABLE_RECORD_RESTART=true      # 녹화 자동 재시작 사용 (true / false)
RECORD_INTERVAL_HOURS=2         # 녹화 재시작 주기 (시간 단위, 기본 2시간, e.g. 2 = 2시간, 1 = 1시간)

# 3. 쿨다운 대기 시간 (초 단위)
STREAM_COOLDOWN_SECONDS=10      # 방송 중단 후 재시작 대기 시간 (초)
RECORD_COOLDOWN_SECONDS=3       # 녹화 중지 후 재시작 대기 시간 (초)

# 4. 재시작 방식 선택:
#    - "stream" : OBS 프로그램은 그대로 켜두고 방송/녹화만 중단 후 재시작 (권장 / 고성능 최적화)
#    - "app"    : OBS 프로그램 앱 자체를 종료 후 재실행 (OBS 앱 메모리 누수 방지용)
MODE="stream"

# 5. OBS WebSocket 연결 설정 (MODE="stream" 일 때만 사용)
#    OBS 메뉴 -> 도구(Tools) -> WebSocket 서버 설정(WebSocket Server Settings)에서 확인
OBS_WS_HOST="127.0.0.1"
OBS_WS_PORT=4455
OBS_WS_PASSWORD="" # WebSocket 비밀번호가 설정되어 있다면 따옴표 안에 입력하세요. 없으면 빈칸 유지.
# ==============================================================================

# 하위 호환성 (이전 변수명 지원)
if [ -n "$RESTART_INTERVAL_HOURS" ] && [ -z "$STREAM_INTERVAL_HOURS" ]; then
    STREAM_INTERVAL_HOURS="$RESTART_INTERVAL_HOURS"
fi

# 스크립트가 위치한 폴더로 이동 (더블클릭 실행 시 필수)
cd "$(dirname "$0")"

# 터미널 창 타이틀 설정
echo -ne "\033]0;OBS 방송/녹화 자동 재시작 매니저 (방송: ${STREAM_INTERVAL_HOURS}h | 녹화: ${RECORD_INTERVAL_HOURS}h)\007"

# 종료 시그널 처리
trap 'echo -e "\n\n[프로그램 종료] 사용자에 의해 자동 재시작 루프가 중단되었습니다."; exit 0' SIGINT SIGTERM

clear
echo "============================================================"
echo "   OBS 24시간 방송 & 녹화 자동 재시작 프로그램 (macOS)       "
echo "============================================================"
echo " - 동작 모드  : $( [ "$MODE" = "stream" ] && echo "송출/녹화 WebSocket 제어 (초경량 최적화)" || echo "OBS 앱 전체 재시작" )"
echo " - 방송 재시작: $( [ "$ENABLE_STREAM_RESTART" = "true" ] && echo "${STREAM_INTERVAL_HOURS} 시간 주기 (활성)" || echo "비활성" )"
echo " - 녹화 재시작: $( [ "$ENABLE_RECORD_RESTART" = "true" ] && echo "${RECORD_INTERVAL_HOURS} 시간 주기 (활성)" || echo "비활성" )"
echo "============================================================"
echo ""

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
        "$PIP_BIN" install --quiet --disable-pip-version-check obsws-python
    fi

    echo "[연결 확인] OBS WebSocket 연결 테스트 중 (${OBS_WS_HOST}:${OBS_WS_PORT})..."
    "$PY_BIN" obs_restarter.py --host "$OBS_WS_HOST" --port "$OBS_WS_PORT" --password "$OBS_WS_PASSWORD" --action status
    if [ $? -ne 0 ]; then
        echo "------------------------------------------------------------"
        echo "[안내] 지금 OBS를 실행하고 WebSocket을 켜시면 정상 연동됩니다."
        echo "루프를 계속 시작합니다 (5초 후 카운트다운 시작)..."
        echo "------------------------------------------------------------"
        sleep 5
    fi
fi

# -------------------------------------------------------------
# 메인 루프 실행 (고성능 단일 프로세스 스케줄러 연동)
# -------------------------------------------------------------
if [ "$MODE" = "stream" ]; then
    # Stream & Record 옵션 플래그 구성
    STREAM_FLAG="--enable-stream"
    if [ "$ENABLE_STREAM_RESTART" != "true" ]; then
        STREAM_FLAG="--disable-stream"
    fi

    RECORD_FLAG=""
    if [ "$ENABLE_RECORD_RESTART" = "true" ]; then
        RECORD_FLAG="--enable-record"
    fi

    # 최적화된 단일 프로세스 파이썬 스케줄러 실행 (CPU 점유율 0% 수렴)
    exec "$PY_BIN" obs_restarter.py \
        --host "$OBS_WS_HOST" \
        --port "$OBS_WS_PORT" \
        --password "$OBS_WS_PASSWORD" \
        --stream-hours "$STREAM_INTERVAL_HOURS" \
        --record-hours "$RECORD_INTERVAL_HOURS" \
        $STREAM_FLAG \
        $RECORD_FLAG \
        --cooldown "$STREAM_COOLDOWN_SECONDS" \
        --record-cooldown "$RECORD_COOLDOWN_SECONDS" \
        --action scheduler

elif [ "$MODE" = "app" ]; then
    # OBS 앱 전체 재실행 모드 (레거시)
    INTERVAL_SECONDS=$(python3 -c "print(int(float('${STREAM_INTERVAL_HOURS}') * 3600))" 2>/dev/null)
    CYCLE_COUNT=0

    while true; do
        CYCLE_COUNT=$((CYCLE_COUNT + 1))
        echo "[사이클 #$CYCLE_COUNT] OBS 프로그램 재실행 대기 (${STREAM_INTERVAL_HOURS}시간 후 재시작)..."
        sleep "$INTERVAL_SECONDS"

        echo "[1/3] OBS 프로그램 종료 중..."
        osascript -e 'quit app "OBS"' 2>/dev/null || killall "OBS" 2>/dev/null
        
        echo "[2/3] ${STREAM_COOLDOWN_SECONDS}초간 대기합니다..."
        sleep "$STREAM_COOLDOWN_SECONDS"

        echo "[3/3] OBS 프로그램 재실행 및 방송 시작 요청..."
        open -a "OBS" --args --startstreaming
        echo ">>> [완료] OBS 재실행 완료 <<<"
    done
fi

