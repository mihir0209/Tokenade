"""Tests for core.session_runtime: policy, webrtc args, oracle snapshot, plan."""
import pytest

from tokenade.core.session_runtime import (
    EgressCheckError,
    RuntimePlanBuilder,
    build_oracle_bootstrap_script,
    enforce_egress,
    resolve_policy,
    webrtc_lockdown_args,
    WEBRTC_LOCKDOWN_ARGS,
)


def _jar(**kw):
    base = {"version": "3.1", "site_name": "example", "cookies": []}
    base.update(kw)
    return base


# --- policy ---


def test_resolve_policy_no_egress():
    assert resolve_policy(_jar()) == {"required": False, "fallback": "direct"}


def test_resolve_policy_default_deny():
    assert resolve_policy(_jar(egress={"mode": "origin-relay"})) == {
        "required": True,
        "fallback": "deny",
    }


def test_resolve_policy_warn_respected():
    p = resolve_policy(_jar(egress={"policy": {"fallback": "warn"}}))
    assert p == {"required": True, "fallback": "warn"}


def test_enforce_egress_ok():
    echo = {"country": "IN", "asn": "AS24560", "ip_hash": "a"}
    hint = {"country": "in", "asn": "as24560", "ip_hash": "a"}
    action, _ = enforce_egress(echo, hint, {"fallback": "deny"})
    assert action == "ok"


def test_enforce_egress_ip_rotation_ok_with_note():
    echo = {"country": "IN", "asn": "AS24560", "ip_hash": "b"}
    hint = {"country": "IN", "asn": "AS24560", "ip_hash": "a"}
    action, msg = enforce_egress(echo, hint, {"fallback": "deny"})
    assert action == "ok" and "rotated" in msg


def test_enforce_egress_deny_and_warn():
    echo = {"country": "GB", "asn": "AS123"}
    hint = {"country": "IN", "asn": "AS24560"}
    action, _ = enforce_egress(echo, hint, {"fallback": "deny"})
    assert action == "deny"
    action, _ = enforce_egress(echo, hint, {"fallback": "warn"})
    assert action == "warn"


# --- webrtc ---


def test_webrtc_args_added_once():
    args = webrtc_lockdown_args(["--no-sandbox"])
    assert WEBRTC_LOCKDOWN_ARGS[0] in args
    assert webrtc_lockdown_args(args).count(WEBRTC_LOCKDOWN_ARGS[0]) == 1


def test_webrtc_user_value_wins():
    custom = "--force-webrtc-ip-handling-policy=default_public_interface_only"
    args = webrtc_lockdown_args([custom])
    assert custom in args and WEBRTC_LOCKDOWN_ARGS[0] not in args


# --- oracle snapshot (Ed25519 roundtrip) ---


def test_snapshot_sign_verify_roundtrip(tmp_path):
    from tokenade.core.session_runtime import (
        generate_origin_keypair,
        sign_snapshot,
        verify_snapshot,
    )

    priv, pub = generate_origin_keypair(tmp_path)
    snap = sign_snapshot({"navigator.platform": "Win32"}, priv, ttl_s=3600)
    ok, reason, age = verify_snapshot(snap, pub)
    assert ok and reason == "valid" and age >= 0


def test_snapshot_tamper_detected(tmp_path):
    from tokenade.core.session_runtime import (
        generate_origin_keypair,
        sign_snapshot,
        verify_snapshot,
    )

    priv, pub = generate_origin_keypair(tmp_path)
    snap = sign_snapshot({"a": 1}, priv)
    snap["values"]["a"] = 2
    ok, reason, _ = verify_snapshot(snap, pub)
    assert not ok and reason == "bad-signature"


def test_snapshot_expiry_is_stale_not_invalid(tmp_path):
    from tokenade.core.session_runtime import (
        generate_origin_keypair,
        sign_snapshot,
        verify_snapshot,
    )

    priv, pub = generate_origin_keypair(tmp_path)
    snap = sign_snapshot({"a": 1}, priv, ttl_s=-1)
    ok, reason, _ = verify_snapshot(snap, pub)
    assert not ok and reason.startswith("valid-stale")


def test_snapshot_key_mismatch(tmp_path):
    from tokenade.core.session_runtime import (
        generate_origin_keypair,
        sign_snapshot,
        verify_snapshot,
    )

    priv, _ = generate_origin_keypair(tmp_path / "a")
    _, pub2 = generate_origin_keypair(tmp_path / "b")
    snap = sign_snapshot({"a": 1}, priv)
    ok, reason, _ = verify_snapshot(snap, pub2)
    assert not ok and reason.startswith("key-mismatch")


# --- plan builder ---


def test_plan_tunnel_without_egress_block_is_hard_error():
    with pytest.raises(EgressCheckError):
        RuntimePlanBuilder().build(_jar(), cli_overrides={"tunnel": "auto"})


def test_plan_unpaired_allowed_with_flag_warns():
    plan = RuntimePlanBuilder().build(
        _jar(), cli_overrides={"tunnel": "auto", "tunnel_allow_unpaired": True}
    )
    assert plan.report["egress_check"]["action"] == "pending"


def test_plan_off_tunnel_plain_jar():
    plan = RuntimePlanBuilder().build(_jar())
    assert plan.proxy is None and plan.oracle["mode"] == "off"
    assert plan.report["fingerprint_source"] == "none"


def test_plan_fingerprint_to_context():
    jar = _jar(fingerprint={"user_agent": "UA", "timezone": "Asia/Kolkata",
                            "language": "en-IN", "bogus_field": 1})
    plan = RuntimePlanBuilder().build(jar)
    assert plan.context_kwargs["user_agent"] == "UA"
    assert plan.context_kwargs["timezone_id"] == "Asia/Kolkata"
    assert plan.cdp_overrides["timezone_id"] == "Asia/Kolkata"
    assert plan.fingerprint_source == "jar"


def test_plan_cli_proxy_beats_tunnel():
    jar = _jar(egress={"mode": "origin-relay"})
    tunnel = {"local_proxy": {"server": "http://127.0.0.1:19001"}}
    plan = RuntimePlanBuilder().build(
        jar, tunnel=tunnel, cli_overrides={"tunnel": "auto", "proxy": {"server": "http://x:8080"}}
    )
    assert plan.proxy == {"server": "http://x:8080"}


def test_plan_tunnel_proxy_and_webrtc():
    jar = _jar(egress={"mode": "origin-relay"})
    tunnel = {"local_proxy": {"server": "http://127.0.0.1:19001"}}
    plan = RuntimePlanBuilder().build(jar, tunnel=tunnel, cli_overrides={"tunnel": "auto"})
    assert plan.context_kwargs["proxy"] == {"server": "http://127.0.0.1:19001"}
    assert WEBRTC_LOCKDOWN_ARGS[0] in plan.launch_args
    assert plan.report["webrtc_lockdown"] is True


def test_plan_egress_deny_raises():
    jar = _jar(egress={"mode": "origin-relay",
                       "origin_hint": {"country": "IN", "asn": "AS1"}})
    tunnel = {"egress_echo": {"country": "GB", "asn": "AS2"}}
    with pytest.raises(EgressCheckError):
        RuntimePlanBuilder().build(jar, tunnel=tunnel, cli_overrides={"tunnel": "auto"})


def test_plan_bootstrap_script_deny_by_default():
    script = build_oracle_bootstrap_script(["navigator.platform"])
    assert "__tokenade_fpq" in script and "ALLOWED" in script
