import socket
from datetime import datetime

HOST = "127.0.0.1"
PORT = 8087

def now():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(1)

    print(f"[{now()}] Listening on {HOST}:{PORT} ...")
    conn, addr = server.accept()
    print(f"[{now()}] Client connected from {addr}")

    # line-based protocol (\r\n terminated)
    f = conn.makefile("rb")
    seq = 1

    try:
        while True:
            raw = f.readline()
            if not raw:
                print(f"[{now()}] Client disconnected")
                break

            msg = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            print(f"[{now()}] RX: {msg}")

            # Send generic "success" response expected by your parser:
            # fields 7/8 => status/error at index 6/7
            # Format: seq;RemoteControl;CMD;timestamp;media;id;status;error
            parts = msg.split(";")
            cmd = parts[3] if len(parts) > 3 else "UNKNOWN"
            req_id = parts[2] if len(parts) > 2 else ""
            resp = f"{seq};RemoteControl;{cmd};0;-1;{req_id};1;\r\n"
            conn.sendall(resp.encode("utf-8"))
            print(f"[{now()}] TX: {resp.strip()}")
            seq += 1

    finally:
        try:
            conn.close()
        except Exception:
            pass
        server.close()

if __name__ == "__main__":
    main()