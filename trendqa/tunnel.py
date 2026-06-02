import os
import io
import time
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


class TunnelManager:
    def __init__(self):
        self._tunnel = None
        self._lock = threading.Lock()
        self._local_port = None
        self._started = False

    def _load_pkey(self):
        import paramiko

        ssh_pkey = os.getenv("SSH_PRIVATE_KEY")
        if ssh_pkey:
            ssh_pkey = ssh_pkey.replace("\\n", "\n")
            key_file = io.StringIO(ssh_pkey)
            for KeyClass in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
                try:
                    key_file.seek(0)
                    return KeyClass.from_private_key(key_file)
                except paramiko.SSHException:
                    continue
            raise paramiko.SSHException("No se pudo cargar la clave SSH privada")
        else:
            return paramiko.RSAKey.from_private_key_file(os.getenv("SSH_KEY_PATH"))

    def _create_tunnel(self):
        from sshtunnel import SSHTunnelForwarder
        import paramiko

        return SSHTunnelForwarder(
            (os.getenv("SSH_HOST"), int(os.getenv("SSH_PORT"))),
            ssh_username=os.getenv("SSH_USER"),
            ssh_pkey=self._load_pkey(),
            remote_bind_address=("127.0.0.1", 3306),
        )

    def start(self):
        with self._lock:
            self._stop_tunnel()
            tunnel = self._create_tunnel()
            tunnel.start()
            self._tunnel = tunnel
            self._local_port = tunnel.local_bind_port
            os.environ["DB_PORT"] = str(self._local_port)
            self._started = True
            logger.info(f"SSH tunnel started on port {self._local_port}")

    def _stop_tunnel(self):
        if self._tunnel is not None:
            try:
                if self._tunnel.is_active:
                    self._tunnel.stop()
            except Exception:
                pass
            self._tunnel = None

    @property
    def local_port(self):
        if not self._started:
            self.start()
        with self._lock:
            if self._tunnel is None or not self._tunnel.is_active:
                logger.warning("SSH tunnel is down, restarting...")
                self.start()
        return self._local_port

    def ensure_alive(self):
        if not self._started:
            self.start()
            return
        with self._lock:
            if self._tunnel is None or not self._tunnel.is_active:
                logger.warning("SSH tunnel is down, restarting...")
                self.start()

    def stop(self):
        with self._lock:
            self._stop_tunnel()
            self._started = False


tunnel_manager = TunnelManager()
