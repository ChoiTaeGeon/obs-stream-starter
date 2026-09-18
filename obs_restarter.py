#!/usr/bin/env python3
"""
OBS Studio 방송 자동 재시작 모듈 (macOS / OBS v28+ WebSocket v5 호환)
"""

import sys
import time
import argparse
import platform
import subprocess

try:
    import obsws_python as obs
except ImportError:
    print("[오류] 'obsws-python' 라이브러리가 필요합니다.")
    print("설치 명령: pip install obsws-python")
    sys.exit(1)


def get_client(host: str, port: int, password: str):
    """OBS WebSocket 클라이언트 연결 (127.0.0.1 / localhost 자동 폴백 지원)"""
    candidate_hosts = [host]
    if host in ("localhost", "127.0.0.1"):
        alt_host = "127.0.0.1" if host == "localhost" else "localhost"
        if alt_host not in candidate_hosts:
            candidate_hosts.append(alt_host)

    last_error = None
    for h in candidate_hosts:
        try:
            kwargs = {"host": h, "port": port}
            if password:
                kwargs["password"] = password
            client = obs.ReqClient(**kwargs)
            return client
        except Exception as e:
            last_error = e

    err_msg = str(last_error)
    if "Connection refused" in err_msg or "61" in err_msg:
        print(f"\n[연결 실패] OBS WebSocket 서버에 연결할 수 없습니다 ({host}:{port}).")
        print("  -> 원인: OBS가 실행 중이지 않거나, WebSocket 서버가 꺼져 있습니다.")
    else:
        print(f"\n[연결 실패] OBS WebSocket 서버에 연결할 수 없습니다 ({host}:{port}).")
        print(f"  -> 원인: {err_msg}")
    print("\n  [해결 방법]")
    print("  1. OBS Studio 프로그램이 켜져 있는지 확인하세요.")
    print("  2. OBS 상단 메뉴 '도구' -> 'WebSocket 서버 설정'을 클릭하세요.")
    print("  3. 'WebSocket 서버 활성화' 체크박스를 켜주세요 (포트: 4455).")
    if password:
        print("  4. 스크립트에 설정한 비밀번호가 OBS WebSocket 비밀번호와 일치하는지 확인하세요.")
    print("")
    return None


def is_streaming(client) -> bool:
    """현재 방송 송출 중인지 확인"""
    try:
        status = client.get_stream_status()
        return bool(status.output_active)
    except Exception as e:
        print(f"[상태 확인 오류] {e}")
        return False


def auto_click_youtube_broadcast() -> bool:
    """macOS에서 OBS YouTube '방송 설정 관리' 팝업 및 '방송 생성 및 시작' 버튼 자동 클릭 (VOD 분할용)"""
    if platform.system() != "Darwin":
        return False

    script = '''
    tell application "System Events"
        if exists (process "OBS") then
            tell process "OBS"
                set frontmost to true
                delay 0.5
                
                -- 1단계: "방송을 진행하기 전에 방송 설정이 필요합니다" 팝업에서 "방송 설정 관리" 클릭
                set foundManage to false
                repeat with w in (get windows)
                    try
                        if exists (button "방송 설정 관리" of w) then
                            click button "방송 설정 관리" of w
                            set foundManage to true
                            exit repeat
                        else if exists (button "Manage Broadcast" of w) then
                            click button "Manage Broadcast" of w
                            set foundManage to true
                            exit repeat
                        end if
                    end try
                end repeat
                
                -- 2단계: "방송 설정 관리" 대화상자에서 "방송 생성 및 시작" 클릭
                repeat 15 times
                    delay 0.6
                    repeat with w in (get windows)
                        try
                            if exists (button "방송 생성 및 시작" of w) then
                                click button "방송 생성 및 시작" of w
                                return "CLICKED_CREATE"
                            else if exists (button "Create broadcast and start streaming" of w) then
                                click button "Create broadcast and start streaming" of w
                                return "CLICKED_CREATE"
                            end if
                        end try
                    end repeat
                end repeat
                
                if foundManage then
                    return "TIMEOUT_CREATE"
                else
                    return "NO_POPUP"
                end if
            end tell
        end if
    end tell
    return "NO_OBS"
    '''
    try:
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=15)
        out = res.stdout.strip()
        if "CLICKED_CREATE" in out:
            return True
    except Exception as e:
        pass
    return False


def restart_stream(host: str, port: int, password: str, cooldown: int = 10) -> bool:
    """방송 중단 후 N초 대기 후 재시작 (YouTube 새 방송 자동 분할 생성 지원)"""
    print(f"\n[작업 시작] OBS WebSocket ({host}:{port}) 연결 중...")
    client = get_client(host, port, password)
    if not client:
        return False

    try:
        active = is_streaming(client)
        if active:
            print("[1/3] 현재 방송이 송출 중입니다. 방송 중단(StopStream) 요청을 보냅니다...")
            print("      (이전 10시간 방송이 종료되며 유튜브 VOD로 안전하게 저장 처리됩니다.)")
            client.stop_stream()
            
            # 송출이 완전히 멈출 때까지 잠시 대기
            for _ in range(15):
                time.sleep(1)
                if not is_streaming(client):
                    print("      방송이 성공적으로 중단되었습니다.")
                    break
            else:
                print("      [주의] 방송 중단 응답 대기 시간이 초과되었으나 계속 진행합니다.")
        else:
            print("[1/3] 현재 방송이 송출 중이 아닙니다. 바로 시작 단계로 넘어갑니다.")

        print(f"[2/3] 유튜브 스트림 분할 및 네트워크 정리를 위해 {cooldown}초간 대기합니다...")
        for remaining in range(cooldown, 0, -1):
            print(f"      새 방송 시작까지 {remaining}초...", end="\r", flush=True)
            time.sleep(1)
        print("      대기 완료!                                      ")

        print("[3/3] 방송 재시작(StartStream) 요청을 보냅니다...")
        try:
            client.start_stream()
        except Exception:
            pass  # 유튜브 브로드캐스트 미설정 시 WebSocket 레벨 응답 예외 허용

        time.sleep(1.5)

        # 바로 방송이 켜지지 않은 경우: YouTube "방송 설정 관리" 팝업 자동 감지 및 새 방송 생성 클릭
        if not is_streaming(client):
            print("      [확인] '방송 설정 관리' 팝업 감지 중... (새 유튜브 방송 자동 생성 시도)")
            clicked = auto_click_youtube_broadcast()
            if clicked:
                print("      [자동 클릭 완료] '방송 설정 관리' -> '새 방송 생성 및 시작' 버튼을 자동으로 클릭했습니다!")
                for _ in range(15):
                    time.sleep(1)
                    if is_streaming(client):
                        break

        if is_streaming(client):
            print(">>> [성공] 새로운 유튜브 방송이 성공적으로 시작되었습니다! (VOD 분할 보존) <<<\n")
            return True
        else:
            print(">>> [경고] 재시작 요청을 보냈으나 방송 활성화 상태가 확인되지 않았습니다. <<<\n")
            return False

    except Exception as e:
        print(f"[오류 발생] 방송 재시작 중 에러: {e}")
        return False


def is_recording(client) -> bool:
    """현재 녹화 중인지 확인"""
    try:
        status = client.get_record_status()
        return bool(status.output_active)
    except Exception as e:
        return False


def restart_record(client_or_host, port: int = 4455, password: str = "", cooldown: int = 3) -> bool:
    """녹화 중단 후 N초 대기 후 재시작"""
    if isinstance(client_or_host, str):
        client = get_client(client_or_host, port, password)
    else:
        client = client_or_host

    if not client:
        return False

    try:
        active = is_recording(client)
        if active:
            print("\n[녹화 재시작 1/3] 기존 녹화 파일 저장 및 중단 요청 (stop_record)...")
            client.stop_record()
            for _ in range(10):
                time.sleep(0.5)
                if not is_recording(client):
                    print("                 녹화가 안전하게 종료되었습니다.")
                    break
        else:
            print("\n[녹화 재시작 1/3] 현재 녹화 중이 아닙니다. 바로 녹화 시작으로 넘어갑니다.")

        print(f"[녹화 재시작 2/3] 파일 인덱싱 및 디스크 저장 대기 ({cooldown}초)...")
        time.sleep(cooldown)

        print("[녹화 재시작 3/3] 새 녹화 시작 요청 (start_record)...")
        client.start_record()
        time.sleep(1)

        if is_recording(client):
            print(">>> [성공] 새로운 녹화 파일 생성이 정상 시작되었습니다! <<<\n")
            return True
        else:
            print(">>> [경고] 녹화 시작 요청을 보냈으나 녹화 상태 활성화가 확인되지 않았습니다. <<<\n")
            return False
    except Exception as e:
        print(f"[오류 발생] 녹화 재시작 중 에러: {e}")
        return False


def check_connection(host: str, port: int, password: str) -> bool:
    """연결 및 상태 점검 (방송 및 녹화 상태 동시 확인)"""
    client = get_client(host, port, password)
    if not client:
        return False
    try:
        streaming = is_streaming(client)
        recording = is_recording(client)
        stream_str = "송출 중" if streaming else "미송출"
        record_str = "녹화 중" if recording else "녹화 중지됨"
        print(f"[연결 성공] OBS 연결 정상 (현재 상태 -> 방송: {stream_str} | 녹화: {record_str})")
        return True
    except Exception as e:
        print(f"[오류] 상태 확인 실패: {e}")
        return False


def format_seconds(seconds: int) -> str:
    """초를 00h 00m 00s 형식으로 변환"""
    if seconds <= 0:
        return "00:00:00"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}시간 {m:02d}분 {s:02d}초"


def run_scheduler(host: str, port: int, password: str,
                  stream_hours: float, record_hours: float,
                  enable_stream: bool, enable_record: bool,
                  stream_cooldown: int = 10, record_cooldown: int = 3):
    """최적화된 단일 프로세스 고성능 스케줄러 (CPU 사용률 0.0% 최적화)"""
    print(f"\n[초기화] OBS WebSocket ({host}:{port}) 연결 확인 중...")
    client = get_client(host, port, password)
    if not client:
        print("[경고] 최초 연결에 실패했습니다. OBS 실행 후 자동으로 재연결을 시도합니다.")

    stream_interval = int(stream_hours * 3600) if enable_stream else 0
    record_interval = int(record_hours * 3600) if enable_record else 0

    now = time.time()
    next_stream_time = now + stream_interval if enable_stream else None
    next_record_time = now + record_interval if enable_record else None

    stream_cycle = 0
    record_cycle = 0

    print("\n============================================================")
    print("        OBS 24시간 자동 재시작 스케줄러 가동 시작           ")
    print("============================================================")
    if enable_stream:
        print(f" [방송 스트림] {stream_hours:g}시간마다 재시작 활성화")
    else:
        print(" [방송 스트림] 재시작 비활성화")

    if enable_record:
        print(f" [동영상 녹화] {record_hours:g}시간마다 재시작 활성화")
    else:
        print(" [동영상 녹화] 재시작 비활성화")
    print("============================================================")
    print(" (중단하려면 이 터미널 창에서 Ctrl + C 를 누르세요)\n")

    while True:
        try:
            now = time.time()

            # 1. 녹화 재시작 주기 도달 확인
            if enable_record and next_record_time and now >= next_record_time:
                record_cycle += 1
                curr_str = time.strftime('%Y-%m-%d %H:%M:%S')
                print(f"\n\n[{curr_str}] [녹화 #{record_cycle}] 녹화 중지 및 재시작 시각 도달!")
                
                # 연결 유효성 확인/재연결
                if not client:
                    client = get_client(host, port, password)
                restart_record(client, port, password, cooldown=record_cooldown)
                
                next_record_time = time.time() + record_interval
                next_rec_str = time.strftime('%H:%M:%S', time.localtime(next_record_time))
                print(f">> 다음 녹화 재시작 예정: {next_rec_str} ({record_hours:g}시간 후)")

            # 2. 방송 재시작 주기 도달 확인
            if enable_stream and next_stream_time and now >= next_stream_time:
                stream_cycle += 1
                curr_str = time.strftime('%Y-%m-%d %H:%M:%S')
                print(f"\n\n[{curr_str}] [방송 #{stream_cycle}] 방송 중단 및 재시작 시각 도달!")
                
                # 연결 유효성 확인/재연결
                if not client:
                    client = get_client(host, port, password)
                restart_stream(client if client else host, port, password, cooldown=stream_cooldown)
                
                next_stream_time = time.time() + stream_interval
                next_stm_str = time.strftime('%H:%M:%S', time.localtime(next_stream_time))
                print(f">> 다음 방송 재시작 예정: {next_stm_str} ({stream_hours:g}시간 후)")

            # 실시간 카운트다운 출력 (터미널 1줄 업데이트로 CPU/출력 최적화)
            status_parts = []
            if enable_stream and next_stream_time:
                rem_stream = max(0, int(next_stream_time - now))
                status_parts.append(f"방송 재시작: {format_seconds(rem_stream)} 남음")
            if enable_record and next_record_time:
                rem_record = max(0, int(next_record_time - now))
                status_parts.append(f"녹화 재시작: {format_seconds(rem_record)} 남음")

            status_line = " | ".join(status_parts)
            sys.stdout.write(f"\r >> {status_line}   ")
            sys.stdout.flush()

            time.sleep(1)

        except KeyboardInterrupt:
            print("\n\n[프로그램 종료] 사용자에 의해 자동 재시작 스케줄러가 중단되었습니다.")
            break
        except Exception as e:
            print(f"\n[루프 오류] {e}")
            time.sleep(3)



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OBS Stream & Recording Controller")
    parser.add_argument("--host", default="127.0.0.1", help="OBS WebSocket 호스트 (기본: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=4455, help="OBS WebSocket 포트 (기본: 4455)")
    parser.add_argument("--password", default="", help="OBS WebSocket 비밀번호")
    parser.add_argument("--cooldown", type=int, default=10, help="방송 중단 후 재시작 대기 시간(초)")
    parser.add_argument("--record-cooldown", type=int, default=3, help="녹화 중지 후 재시작 대기 시간(초)")
    parser.add_argument("--stream-hours", type=float, default=5.0, help="방송 재시작 주기(시간)")
    parser.add_argument("--record-hours", type=float, default=2.0, help="녹화 재시작 주기(시간)")
    parser.add_argument("--enable-stream", action="store_true", default=True, help="방송 자동 재시작 활성화")
    parser.add_argument("--disable-stream", dest="enable_stream", action="store_false", help="방송 자동 재시작 비활성화")
    parser.add_argument("--enable-record", action="store_true", default=False, help="녹화 자동 재시작 활성화")
    parser.add_argument("--action", choices=[
        "scheduler", "restart", "restart-record", "status",
        "stop", "start", "stop-record", "start-record"
    ], default="scheduler")

    args = parser.parse_args()

    if args.action == "status":
        success = check_connection(args.host, args.port, args.password)
        sys.exit(0 if success else 1)
    elif args.action == "restart":
        success = restart_stream(args.host, args.port, args.password, args.cooldown)
        sys.exit(0 if success else 1)
    elif args.action == "restart-record":
        success = restart_record(args.host, args.port, args.password, args.record_cooldown)
        sys.exit(0 if success else 1)
    elif args.action == "stop":
        c = get_client(args.host, args.port, args.password)
        if c:
            c.stop_stream()
            print("방송 중단 요청 완료")
    elif args.action == "start":
        c = get_client(args.host, args.port, args.password)
        if c:
            c.start_stream()
            print("방송 시작 요청 완료")
    elif args.action == "stop-record":
        c = get_client(args.host, args.port, args.password)
        if c:
            c.stop_record()
            print("녹화 중지 요청 완료")
    elif args.action == "start-record":
        c = get_client(args.host, args.port, args.password)
        if c:
            c.start_record()
            print("녹화 시작 요청 완료")
    elif args.action == "scheduler":
        run_scheduler(
            host=args.host,
            port=args.port,
            password=args.password,
            stream_hours=args.stream_hours,
            record_hours=args.record_hours,
            enable_stream=args.enable_stream,
            enable_record=args.enable_record,
            stream_cooldown=args.cooldown,
            record_cooldown=args.record_cooldown
        )

