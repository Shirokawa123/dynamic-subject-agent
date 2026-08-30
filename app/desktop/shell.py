"""Desktop shell launcher (slice-05).

Starts the local serving layer on an ephemeral loopback port, then opens the
desktop window: pywebview if installed, otherwise Edge app-mode (no browser
chrome, a real standalone window), otherwise the default browser.
"""

from __future__ import annotations

import subprocess
import threading
import webbrowser
from pathlib import Path

from server import AppState, build_handler, build_product


def _open_window(url: str) -> None:
    try:
        import webview  # type: ignore

        webview.create_window("Avery", url, width=900, height=760)
        webview.start()
        return
    except ImportError:
        pass
    for candidate in (
        Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
        Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
    ):
        if candidate.exists():
            subprocess.Popen(
                [str(candidate), f"--app={url}", "--window-size=920,780"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
    webbrowser.open(url)


def main() -> int:
    product = build_product(relationship_mode="dynamic")

    from http.server import ThreadingHTTPServer

    state = AppState(product)
    server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(state))
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/"
    print(f"Avery 已就绪：{url}（关闭窗口后按 Ctrl+C 退出）")

    threading.Thread(
        target=lambda: _open_window(url), daemon=True
    ).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        product.close()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
