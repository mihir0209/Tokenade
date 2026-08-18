#!/usr/bin/env python3
"""
Advanced Session Workflow Demo.

Demonstrates:
1. Packaging a multi-tier session (Cookies + LocalStorage + SessionStorage + IndexedDB)
2. Memory Key Zeroization via SecureBuffer
3. Encrypted & Compressed Vault Operations (gzip/zlib)
4. S3/R2 Session Synchronization pipeline
"""

import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tokenade.core.crypto.secure_memory import SecureBuffer, zero_memory
from tokenade.core.importer.session_packager import SessionPackager
from tokenade.core.importer.session_vault import SessionVault
from tokenade.core.sync.syncer import SessionSyncer, SyncConfig


def main():
    print("=== Tokenade v1.3.0 Advanced Session Workflow ===")

    # 1. Package rich multi-origin session with IndexedDB
    packager = SessionPackager()
    cookies = [
        {"name": "session_id", "value": "demo_live_token_123", "domain": "app.tokenade.dev", "path": "/"},
        {"name": "user_id", "value": "usr_alpha_99", "domain": "app.tokenade.dev", "path": "/"}
    ]
    local_storage = {"theme": "cyberpunk", "analytics_consent": "true"}
    session_storage = {"active_tab": "dashboard_view"}
    indexeddb_data = {
        "app_cache_db": {
            "version": 1,
            "stores": {
                "user_credentials": {"auth_jwt": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."},
                "offline_cache": {"records_count": 42}
            }
        }
    }

    print("\n1. Packaging Session with Full Web Storage & IndexedDB...")
    pkg = packager.package(
        cookies=cookies,
        local_storage=local_storage,
        session_storage=session_storage,
        indexeddb=indexeddb_data,
        browser="chromium",
        profile="default",
    )
    print(f"   ✓ Generated .tokenade v{pkg['version']} for {pkg['site_name']}")
    print(f"   ✓ Storage keys captured: local={len(pkg['storage']['local'])}, session={len(pkg['storage']['session'])}, idb={len(pkg['storage']['indexeddb'])}")

    # 2. Ephemeral In-Memory Secret Zeroization
    print("\n2. Demonstrating Cryptographic Memory Zeroization...")
    secret_key = b"super_secret_master_aes256_key_to_wipe"
    with SecureBuffer(secret_key) as sbuf:
        print(f"   ✓ Active in SecureBuffer: {sbuf.raw_bytes[:12]}...")
        # Inside buffer is safe
    print("   ✓ Buffer zeroized and wiped from memory upon context exit")

    # 3. Compressed Session Vault Storage
    with tempfile.TemporaryDirectory() as tmp_vault_dir:
        print("\n3. Storing Session in Compressed Vault (gzip)...")
        vault = SessionVault(vault_dir=tmp_vault_dir, compression="gzip")

        with tempfile.NamedTemporaryFile(suffix=".tokenade", mode="w", delete=False) as tmp_session:
            json.dump(pkg, tmp_session)
            tmp_session_path = tmp_session.name

        session_id = vault.add(tmp_session_path, tags=["demo", "indexeddb", "v1.3.0"])
        print(f"   ✓ Session stored in vault with ID: {session_id}")

        retrieved = vault.get(session_id)
        assert retrieved is not None
        print(f"   ✓ Retrieved and decompressed successfully ({len(retrieved.get('cookies', []))} cookies)")
        os.unlink(tmp_session_path)

    # 4. S3/R2 Cloud Transport Setup
    print("\n4. Session Synchronization Pipeline...")
    sync_config = SyncConfig(
        transport="s3",
        s3_bucket="my-tokenade-cloud-vault",
        s3_endpoint_url="https://r2.cloudflarestorage.com",
    )
    syncer = SessionSyncer(sync_config)
    transport = syncer._get_transport()
    print(f"   ✓ Configured cloud transport: {transport.__class__.__name__} -> bucket: {transport.bucket}")

    print("\nWorkflow completed successfully!")


if __name__ == "__main__":
    main()
