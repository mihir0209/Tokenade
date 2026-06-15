"""
Performance Benchmarks - Measures extraction speed, proxy throughput, encryption speed.
"""

import time
import json
import tempfile
import os
from pathlib import Path


def benchmark_extraction():
    """Benchmark cookie extraction speed."""
    from tokenade.core.importer.cookie_extractor import CookieExtractor
    
    try:
        # Find Firefox profile
        firefox_path = os.path.expanduser("~/.snap/firefox/common/.mozilla/firefox")
        if not os.path.exists(firefox_path):
            firefox_path = os.path.expanduser("~/.mozilla/firefox")
        
        profiles_dir = Path(firefox_path)
        default_profile = None
        for p in profiles_dir.iterdir():
            if p.is_dir() and "default" in p.name.lower():
                default_profile = p
                break
        
        if not default_profile:
            print("  No Firefox profile found, skipping")
            return {"browser": "none", "cookies": 0, "time": 0, "speed": 0}
        
        print(f"  Using: firefox ({default_profile.name})")
        extractor = CookieExtractor(str(default_profile))
        
        start = time.time()
        cookies = extractor.extract()
        elapsed = time.time() - start
        count = len(cookies) if cookies else 0
        speed = count / elapsed if elapsed > 0 else 0
        print(f"  Firefox: {count} cookies in {elapsed:.2f}s ({speed:.0f} cookies/s)")
        return {"browser": "firefox", "cookies": count, "time": elapsed, "speed": speed}
    except Exception as e:
        print(f"  Firefox: FAILED ({e})")
        return {"browser": "firefox", "error": str(e)}


def benchmark_packaging():
    """Benchmark session packaging speed."""
    from tokenade.core.importer.session_packager import SessionPackager
    
    packager = SessionPackager()
    
    # Create test cookies
    cookies = [
        {"name": f"cookie_{i}", "value": f"value_{i}", "domain": ".example.com", "path": "/"}
        for i in range(1000)
    ]
    
    # Benchmark packaging
    start = time.time()
    session = packager.package(cookies)
    elapsed = time.time() - start
    speed = len(cookies) / elapsed if elapsed > 0 else 0
    print(f"  Package 1000 cookies: {elapsed:.3f}s ({speed:.0f} cookies/s)")
    
    # Benchmark saving
    with tempfile.NamedTemporaryFile(suffix=".tokenade", delete=False) as f:
        tmp_path = f.name
    
    start = time.time()
    packager.save(session, tmp_path)
    save_time = time.time() - start
    file_size = os.path.getsize(tmp_path)
    print(f"  Save session: {save_time:.3f}s ({file_size} bytes)")
    
    # Benchmark loading
    start = time.time()
    loaded = packager.load(tmp_path)
    load_time = time.time() - start
    print(f"  Load session: {load_time:.3f}s")
    
    os.unlink(tmp_path)
    
    return {
        "package_time": elapsed,
        "save_time": save_time,
        "load_time": load_time,
        "file_size": file_size
    }


def benchmark_encryption():
    """Benchmark encryption/decryption speed."""
    from tokenade.core.crypto.encryptor import TokenadeEncryptor
    
    encryptor = TokenadeEncryptor()
    
    # Create test data
    test_data = json.dumps({"cookies": [{"name": f"c{i}", "value": "x" * 100} for i in range(100)]}).encode()
    
    # Benchmark encryption
    start = time.time()
    encrypted = encryptor.encrypt(test_data, "benchmark_password")
    enc_time = time.time() - start
    print(f"  Encrypt {len(test_data)} bytes: {enc_time:.3f}s")
    
    # Benchmark decryption
    start = time.time()
    decrypted = encryptor.decrypt(encrypted, "benchmark_password")
    dec_time = time.time() - start
    print(f"  Decrypt {len(encrypted)} bytes: {dec_time:.3f}s")
    
    assert decrypted == test_data, "Decryption mismatch!"
    
    return {"encrypt_time": enc_time, "decrypt_time": dec_time}


def benchmark_health_check():
    """Benchmark health check speed."""
    from tokenade.core.refresh.health_checker import SessionHealthChecker
    
    checker = SessionHealthChecker()
    
    # Create test session
    session = {
        "cookies": [
            {"name": f"cookie_{i}", "value": "x" * 50, "domain": ".example.com",
             "expires": time.time() + 86400 * (30 - i), "secure": True, "httpOnly": True}
            for i in range(100)
        ]
    }
    
    start = time.time()
    result = checker.check_session(session)
    elapsed = time.time() - start
    print(f"  Health check 100 cookies: {elapsed:.3f}s")
    
    return {"time": elapsed}


def benchmark_tls_matcher():
    """Benchmark TLS matcher initialization."""
    from tokenade.core.runtime.tls_matcher import TLSMatcher
    
    start = time.time()
    matcher = TLSMatcher()
    init_time = time.time() - start
    print(f"  TLS matcher init: {init_time:.3f}s")
    
    # Benchmark a request
    start = time.time()
    try:
        resp = matcher.get("https://httpbin.org/get", timeout=10)
        req_time = time.time() - start
        print(f"  TLS request (httpbin): {req_time:.3f}s ({resp.status_code})")
    except Exception as e:
        req_time = time.time() - start
        print(f"  TLS request: FAILED in {req_time:.3f}s ({e})")
    
    matcher.close()
    return {"init_time": init_time, "request_time": req_time}


def run_all_benchmarks():
    """Run all benchmarks."""
    print("=" * 60)
    print("TOKENADE PERFORMANCE BENCHMARKS")
    print("=" * 60)
    
    results = {}
    
    print("\n1. Cookie Extraction")
    print("-" * 40)
    results["extraction"] = benchmark_extraction()
    
    print("\n2. Session Packaging")
    print("-" * 40)
    results["packaging"] = benchmark_packaging()
    
    print("\n3. Encryption/Decryption")
    print("-" * 40)
    results["encryption"] = benchmark_encryption()
    
    print("\n4. Health Check")
    print("-" * 40)
    results["health"] = benchmark_health_check()
    
    print("\n5. TLS Matcher")
    print("-" * 40)
    results["tls"] = benchmark_tls_matcher()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    if "extraction" in results and "speed" in results["extraction"]:
        print(f"  Extraction: {results['extraction']['speed']:.0f} cookies/s")
    print(f"  Packaging: {results['packaging']['package_time']:.3f}s for 1000 cookies")
    print(f"  Encryption: {results['encryption']['encrypt_time']:.3f}s")
    print(f"  Decryption: {results['encryption']['decrypt_time']:.3f}s")
    print(f"  Health Check: {results['health']['time']:.3f}s")
    print(f"  TLS Init: {results['tls']['init_time']:.3f}s")
    
    return results


if __name__ == "__main__":
    run_all_benchmarks()
