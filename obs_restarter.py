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
    """OBS WebSocket 클라이언트 연결"""
    try:
        # obsws-python ReqClient 연결
        kwargs = {"host": host, "port": port}
        if password:
            kwargs["password"] = password
        client = obs.ReqClient(**kwargs)
        return client
    except Exception as e:
        print(f"[연결 실패] OBS WebSocket 서버에 연결할 수 없습니다 ({host}:{port}).")
        print(f"  원인: {e}")
        print("  팁: OBS가 실행 중인지, '도구 > WebSocket 서버 설정'에서 서버가 활성화되어 있는지 확인하세요.")
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
    parser.add_argument("--host", default="localhost", help="OBS WebSocket 호스트 (기본: localhost)")
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
