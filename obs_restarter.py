#!/usr/bin/env python3
"""
OBS Studio 방송 자동 재시작 모듈 (macOS / OBS v28+ WebSocket v5 호환)
"""

import sys
import time
import argparse

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


def restart_stream(host: str, port: int, password: str, cooldown: int = 10) -> bool:
    """방송 중단 후 N초 대기 후 재시작"""
    print(f"\n[작업 시작] OBS WebSocket ({host}:{port}) 연결 중...")
    client = get_client(host, port, password)
    if not client:
        return False

    try:
        active = is_streaming(client)
        if active:
            print("[1/3] 현재 방송이 송출 중입니다. 방송 중단(StopStream) 요청을 보냅니다...")
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

        print(f"[2/3] 스트림 버퍼 및 네트워크 정리를 위해 {cooldown}초간 대기합니다...")
        for remaining in range(cooldown, 0, -1):
            print(f"      재시작까지 {remaining}초...", end="\r", flush=True)
            time.sleep(1)
        print("      대기 완료!                                      ")

        print("[3/3] 방송 재시작(StartStream) 요청을 보냅니다...")
        client.start_stream()
        time.sleep(2)

        if is_streaming(client):
            print(">>> [성공] 방송이 성공적으로 다시 시작되었습니다! <<<\n")
            return True
        else:
            print(">>> [경고] 재시작 요청을 보냈으나 방송 활성화 상태가 확인되지 않았습니다. <<<\n")
            return False

    except Exception as e:
        print(f"[오류 발생] 방송 재시작 중 에러: {e}")
        return False


def check_connection(host: str, port: int, password: str) -> bool:
    """연결 및 상태 점검"""
    client = get_client(host, port, password)
    if not client:
        return False
    try:
        active = is_streaming(client)
        status_str = "방송 중" if active else "방송 대기 중(미송출)"
        print(f"[연결 성공] OBS 연결 정상 (현재 상태: {status_str})")
        return True
    except Exception as e:
        print(f"[오류] 상태 확인 실패: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OBS Stream Controller")
    parser.add_argument("--host", default="127.0.0.1", help="OBS WebSocket 호스트 (기본: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=4455, help="OBS WebSocket 포트 (기본: 4455)")
    parser.add_argument("--password", default="", help="OBS WebSocket 비밀번호")
    parser.add_argument("--cooldown", type=int, default=10, help="중단 후 재시작 대기 시간(초)")
    parser.add_argument("--action", choices=["restart", "status", "stop", "start"], default="restart")

    args = parser.parse_args()

    if args.action == "status":
        success = check_connection(args.host, args.port, args.password)
        sys.exit(0 if success else 1)
    elif args.action == "restart":
        success = restart_stream(args.host, args.port, args.password, args.cooldown)
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
