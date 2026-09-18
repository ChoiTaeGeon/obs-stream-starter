#!/bin/bash
# ==============================================================================
# [OBS 동영상 녹화 전용 자동 재시작 스크립트 (macOS Intel/Apple Silicon 겸용)]
# Finder에서 이 파일(start_record_restarter.command)을 더블클릭하여 실행하십시오.
# ==============================================================================

# ==============================================================================
# [★ 사용자 설정 영역 - 원하는 값으로 수정하세요]
# ==============================================================================
# 1. 녹화 재시작 주기 (시간 단위, 소수점 가능 e.g. 2 = 2시간, 1 = 1시간, 0.5 = 30분)
RECORD_INTERVAL_HOURS=2

# 2. 녹화 중지 후 재시작 전 대기 시간 (초 단위, 디스크 저장 및 인덱싱 대기)
RECORD_COOLDOWN_SECONDS=3

# 3. OBS WebSocket 연결 설정
#    OBS 메뉴 -> 도구(Tools) -> WebSocket 서버 설정(WebSocket Server Settings)에서 확인
OBS_WS_HOST="127.0.0.1"
OBS_WS_PORT=4455
OBS_WS_PASSWORD="" # WebSocket 비밀번호가 설정되어 있다면 따옴표 안에 입력하세요. 없으면 빈칸 유지.
# ==============================================================================

# 스크립트가 위치한 폴더로 이동 (더블클릭 실행 시 필수)
cd "$(dirname "$0")"

# 터미널 창 타이틀 설정
echo -ne "\033]0;OBS 녹화 전용 자동 재시작 매니저 (주기: ${RECORD_INTERVAL_HOURS}시간)\007"

# 종료 시그널 처리
trap 'echo -e "\n\n[프로그램 종료] 사용자에 의해 녹화 자동 재시작 루프가 중단되었습니다."; exit 0' SIGINT SIGTERM

clear
echo "============================================================"
echo "      OBS 동영상 녹화 전용 자동 재시작 프로그램 (macOS)     "
echo "============================================================"
echo " - 녹화 재시작 주기: ${RECORD_INTERVAL_HOURS} 시간"
echo " - 재시작 쿨다운   : ${RECORD_COOLDOWN_SECONDS} 초"
echo " - 연결 대상       : ${OBS_WS_HOST}:${OBS_WS_PORT}"
echo "============================================================"
echo ""

# Python 3 확인
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

# 녹화 전용 고성능 스케줄러 실행 (방송은 비활성화하고 녹화만 단독 실행)
exec "$PY_BIN" obs_restarter.py \
    --host "$OBS_WS_HOST" \
    --port "$OBS_WS_PORT" \
    --password "$OBS_WS_PASSWORD" \
    --disable-stream \
    --enable-record \
    --record-hours "$RECORD_INTERVAL_HOURS" \
    --record-cooldown "$RECORD_COOLDOWN_SECONDS" \
    --action scheduler
