"""
Transparent encryption at rest for session files.

Automatically encrypts sessions on save and decrypts on load
when encryption is configured. Uses TokenadeEncryptor (AES-256-GCM).
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger(__name__)


def is_encrypted_file(file_path: str) -> bool:
    """Check if a file is encrypted by looking for the TOKENADE_ENCRYPTED magic header."""
    try:
        with open(file_path, "rb") as f:
            header = f.read(20)
        return header.startswith(b"TOKENADE_ENCRYPTED")
    except (OSError, IOError):
        return False


def get_encryption_password(
    password: Optional[str] = None,
    key_file: Optional[str] = None,
) -> Optional[str]:
    """
    Resolve encryption password from arguments, config, or environment.

    Priority:
    1. Explicit password argument
    2. Key file contents
    3. TOKENADE_PASSWORD environment variable
    4. Config file encryption_password
    5. Config file encryption_key_file
    """
    if password:
        return password

    if key_file:
        from tokenade.core.crypto.encryptor import load_key_from_file
        return load_key_from_file(key_file)

    env_password = os.environ.get("TOKENADE_PASSWORD")
    if env_password:
        return env_password

    try:
        from tokenade.core.config import load_config
        config = load_config()

        cfg_key_file = config.get("encryption_key_file")
        if cfg_key_file and Path(cfg_key_file).exists():
            from tokenade.core.crypto.encryptor import load_key_from_file
            return load_key_from_file(cfg_key_file)

        cfg_password = config.get("encryption_password")
        if cfg_password:
            return cfg_password
    except Exception:
        pass

    return None


def should_encrypt() -> bool:
    """Check if encryption is enabled by default in config."""
    try:
        from tokenade.core.config import load_config
        config = load_config()
        return config.get("encrypt_by_default", False)
    except Exception:
        return False


def encrypt_session_data(session_data: Dict, password: str) -> bytes:
    """Encrypt session dictionary to encrypted bytes."""
    import json as _json
    from tokenade.core.crypto.encryptor import TokenadeEncryptor

    json_bytes = _json.dumps(session_data, indent=2, ensure_ascii=False).encode("utf-8")
    encryptor = TokenadeEncryptor()
    return encryptor.encrypt(json_bytes, password)


def decrypt_session_data(encrypted_bytes: bytes, password: str) -> Dict:
    """Decrypt encrypted bytes to session dictionary."""
    import json as _json
    from tokenade.core.crypto.encryptor import TokenadeEncryptor

    encryptor = TokenadeEncryptor()
    decrypted = encryptor.decrypt(encrypted_bytes, password)
    return _json.loads(decrypted.decode("utf-8"))


def save_encrypted(
    session_data: Dict,
    output_path: str,
    password: Optional[str] = None,
    key_file: Optional[str] = None,
) -> str:
    """
    Save session data to an encrypted file.

    Args:
        session_data: Session dictionary to save
        output_path: Path to write encrypted file
        password: Encryption password (resolved from config if not provided)
        key_file: Path to key file (alternative to password)

    Returns:
        Absolute path to saved file

    Raises:
        ValueError: If no password can be resolved
    """
    resolved_password = get_encryption_password(password, key_file)
    if not resolved_password:
        raise ValueError(
            "No encryption password available. Provide --password, --key-file, "
            "set TOKENADE_PASSWORD env var, or configure encryption_password "
            "in ~/.tokenade/config.json"
        )

    encrypted = encrypt_session_data(session_data, resolved_password)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    umask = os.umask(0o177)
    try:
        with open(path, "wb") as f:
            f.write(encrypted)
    finally:
        os.umask(umask)

    logger.info(f"Session saved (encrypted): {path}")
    return str(path.absolute())


def load_encrypted(
    file_path: str,
    password: Optional[str] = None,
    key_file: Optional[str] = None,
) -> Dict:
    """
    Load session data from an encrypted file.

    Args:
        file_path: Path to encrypted file
        password: Decryption password (resolved from config if not provided)
        key_file: Path to key file (alternative to password)

    Returns:
        Session dictionary

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If no password can be resolved or decryption fails
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Session file not found: {file_path}")

    resolved_password = get_encryption_password(password, key_file)
    if not resolved_password:
        raise ValueError(
            "No decryption password available. Provide --password, --key-file, "
            "set TOKENADE_PASSWORD env var, or configure encryption_password "
            "in ~/.tokenade/config.json"
        )

    encrypted_bytes = path.read_bytes()
    return decrypt_session_data(encrypted_bytes, resolved_password)
