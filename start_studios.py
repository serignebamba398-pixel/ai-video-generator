"""Start two independent studios. Ctrl+C stops both child processes."""

import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent
PORTS = (8501, 8502)


def main():
    load_dotenv(ROOT / ".env")
    for name in ("AGNES_API_KEY", "AGNES_API_KEY2"):
        if not os.getenv(name, "").strip():
            print(f"Ajoute {name} dans .env avant de lancer les studios.")
            return 1
    for port in PORTS:
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                print(f"Le port {port} est occupe. Arrete son serveur puis relance.")
                return 1

    processes = []
    try:
        for instance, port in enumerate(PORTS, start=1):
            env = os.environ.copy()
            env["STUDIO_INSTANCE"] = str(instance)
            processes.append(subprocess.Popen(
                [sys.executable, "-u", "-m", "streamlit", "run", str(ROOT / "app.py"),
                 f"--server.port={port}", "--server.address=127.0.0.1",
                 "--server.headless=true", "--browser.gatherUsageStats=false"],
                cwd=ROOT, env=env,
            ))
        pending = set(PORTS)
        deadline = time.monotonic() + 60
        print("Demarrage des deux studios. Ctrl+C pour les arreter.", flush=True)
        while True:
            for process in processes:
                if process.poll() is not None:
                    raise RuntimeError("Un studio s'est arrete. Consulte les messages ci-dessus.")
            for port in tuple(pending):
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/_stcore/health", timeout=1
                    ) as response:
                        if response.status != 200:
                            continue
                except (OSError, urllib.error.URLError):
                    continue
                url = f"http://localhost:{port}"
                print(f"Studio {PORTS.index(port) + 1} : {url}", flush=True)
                webbrowser.open_new_tab(url)
                pending.remove(port)
            if pending and time.monotonic() > deadline:
                raise RuntimeError("Les studios n'ont pas demarre dans le delai de 60 secondes.")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nArret des deux studios.")
        return 0
    except Exception as exc:
        print(f"Erreur : {exc}")
        return 1
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    sys.exit(main())
