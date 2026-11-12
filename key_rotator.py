import os
import sys
import time
import uuid
import random
import asyncio
import collections
from typing import List, Dict, Tuple, Any, Optional
import dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Load environment variables from .env
dotenv.load_dotenv()


class PoolExhaustedError(RuntimeError):
    """Raised when all credentials in a provider pool are rate-limited, quarantined, or TPM-exhausted."""
    def __init__(self, provider_name: str, reason: str, soonest_available_in: float = 0.0):
        super().__init__(f"[{provider_name}] Pool exhausted: {reason}. Soonest available in {soonest_available_in:.1f}s.")
        self.provider_name = provider_name
        self.reason = reason
        self.soonest_available_in = soonest_available_in


class KeyLease:
    """
    Atomic reservation lease for an API credential.
    Tracks in-flight slot, estimated tokens, and reconciles actual tokens / 429 cooldowns upon completion.
    """
    def __init__(
        self,
        pool: Any,
        lease_id: str,
        key_index: int,
        credential: Any,
        estimated_tokens: int,
        reserved_at: float
    ):
        self.pool = pool
        self.lease_id = lease_id
        self.key_index = key_index
        self.credential = credential
        self.estimated_tokens = max(1, estimated_tokens)
        self.reserved_at = reserved_at
        self._released = False
        self._tokens_reconciled = False
        self._error_recorded = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                err_str = str(exc_val).lower()
                is_429 = "429" in err_str or "rate limit" in err_str or "resource_exhausted" in err_str or "quota" in err_str
                is_invalid_key = (
                    "invalid api key" in err_str
                    or "api_key_invalid" in err_str
                    or "api key not valid" in err_str
                    or "key expired" in err_str
                    or "revoked" in err_str
                    or ("401" in err_str and "model" not in err_str)
                )
                # Codex fix 1 & 2: Preserve estimated tokens on exception (since provider likely consumed prompt)
                # and record error states independently
                self.record_outcome(
                    actual_tokens=self.estimated_tokens,
                    rate_limited=is_429,
                    permanent_error=is_invalid_key
                )
            else:
                if not self._tokens_reconciled:
                    self.record_outcome(actual_tokens=self.estimated_tokens)
        finally:
            self.release()

    def record_outcome(
        self,
        actual_tokens: Optional[int] = None,
        rate_limited: bool = False,
        retry_after: Optional[float] = None,
        permanent_error: bool = False
    ):
        """Records call metrics and rate-limiting outcomes independently and idempotently."""
        reconcile_tok = None
        if actual_tokens is not None and not self._tokens_reconciled:
            self._tokens_reconciled = True
            reconcile_tok = max(0, actual_tokens)

        rec_rate_limited = False
        rec_perm = False
        if (rate_limited or permanent_error) and not self._error_recorded:
            self._error_recorded = True
            rec_rate_limited = rate_limited
            rec_perm = permanent_error

        if reconcile_tok is not None or rec_rate_limited or rec_perm:
            self.pool._reconcile_outcome(
                lease_id=self.lease_id,
                key_index=self.key_index,
                actual_tokens=reconcile_tok,
                rate_limited=rec_rate_limited,
                retry_after=retry_after,
                permanent_error=rec_perm
            )

    def release(self):
        """Releases the in-flight concurrency slot on the credential."""
        if self._released:
            return
        self._released = True
        self.pool._release_in_flight(self.key_index, self.lease_id)


class ProviderKeyPool:
    """
    Manages a pool of API keys for a specific provider with:
    - Atomic non-blocking reservation leases (KeyLease) with unique lease IDs
    - Sliding 60s window tracking for RPM and TPM per key
    - Shared provider/account-wide TPM cap enforcement
    - Fast non-blocking failover (PoolExhaustedError in <10ms instead of sleeping inside locks)
    - Per-key interval pacing and in-flight concurrency limits
    - Monotonically increasing cooldowns respecting provider Retry-After
    - Idempotent reservation ledger reconciliation
    """
    def __init__(
        self,
        provider_name: str,
        keys: List[Any],
        soft_rpm_per_key: int = 20,
        soft_tpm_per_key: int = 6000,
        shared_account_tpm: int = 18000,
        min_interval_sec: float = 1.2,
        max_in_flight_per_key: int = 1,
        keys_are_independent_accounts: bool = False
    ):
        self.provider_name = provider_name
        self.keys_are_independent_accounts = keys_are_independent_accounts
        deduped: List[Any] = []
        for k in keys:
            norm = k.strip() if isinstance(k, str) else k
            if norm and norm not in deduped:
                deduped.append(norm)
        self.keys = deduped

        self.soft_rpm_per_key = max(1, soft_rpm_per_key)
        self.soft_tpm_per_key = max(100, soft_tpm_per_key)
        self.shared_account_tpm = max(self.soft_tpm_per_key, shared_account_tpm)
        self.min_interval_sec = max(0.0, min_interval_sec)
        self.max_in_flight_per_key = max(1, max_in_flight_per_key)

        self._index = 0
        self._lock = asyncio.Lock()

        n = len(self.keys)
        self._req_timestamps: List[collections.deque] = [collections.deque() for _ in range(n)]
        self._token_ledger: List[collections.deque] = [collections.deque() for _ in range(n)]
        self._active_reservations: Dict[str, Dict[str, Any]] = {}

        self._last_used: List[float] = [0.0] * n
        self._cooldown_until: List[float] = [0.0] * n
        self._in_flight: List[int] = [0] * n
        self._quarantined: List[bool] = [False] * n
        self._total_calls: List[int] = [0] * n
        self._total_429s: List[int] = [0] * n

    @property
    def total_keys(self) -> int:
        return len(self.keys)

    def _prune_sliding_windows(self, now: float):
        """Removes entries older than 60 seconds from RPM and TPM windows."""
        cutoff = now - 60.0
        for i in range(len(self.keys)):
            ts_q = self._req_timestamps[i]
            while ts_q and ts_q[0] < cutoff:
                ts_q.popleft()
            tok_q = self._token_ledger[i]
            while tok_q and tok_q[0]["timestamp"] < cutoff:
                expired_item = tok_q.popleft()
                self._active_reservations.pop(expired_item["id"], None)

    def _get_key_rolling_tpm(self, key_idx: int) -> int:
        return sum(item["tokens"] for item in self._token_ledger[key_idx])

    def calculate_pacing_delay(self, estimated_tokens: int, utilization: float = 0.8) -> float:
        """
        Calculates mathematical delay pacing per request according to the empirical pacing formula:
        Delta_t = (1 / u) * max(60 / soft_rpm, (60 * est_tokens) / soft_tpm)
        Respects provider token capacity and burst rates without relying on arbitrary delays.
        """
        rpm_pacing = 60.0 / max(1.0, float(self.soft_rpm_per_key))
        tpm_pacing = (60.0 * max(10, estimated_tokens)) / max(100.0, float(self.soft_tpm_per_key))
        u = max(0.1, min(1.0, utilization))
        return max(self.min_interval_sec, (1.0 / u) * max(rpm_pacing, tpm_pacing))

    def _get_account_rolling_tpm(self) -> int:
        return sum(sum(item["tokens"] for item in q) for q in self._token_ledger)

    async def acquire_lease(
        self,
        estimated_tokens: int = 1500,
        max_wait_sec: float = 0.0
    ) -> KeyLease:
        """
        Atomically selects and reserves the next available key lease.
        If all keys are exhausted, rate-limited, or TPM-full, raises PoolExhaustedError immediately.
        """
        if not self.keys:
            raise PoolExhaustedError(self.provider_name, "no_keys_configured", 0.0)

        est_tok = max(1, estimated_tokens)

        total_waited = 0.0
        while True:
            wait_to_sleep = 0.0
            async with self._lock:
                now = time.monotonic()
                self._prune_sliding_windows(now)

                acct_tpm = self._get_account_rolling_tpm()
                # If keys belong to independent accounts, skip shared account TPM bottleneck
                if not self.keys_are_independent_accounts and (acct_tpm + est_tok > self.shared_account_tpm):
                    oldest_ts = now
                    for q in self._token_ledger:
                        if q:
                            oldest_ts = min(oldest_ts, q[0]["timestamp"])
                    wait_roll = max(0.5, (oldest_ts + 60.0) - now)
                    remaining = max_wait_sec - total_waited
                    if remaining >= wait_roll:
                        wait_to_sleep = wait_roll
                    else:
                        raise PoolExhaustedError(
                            self.provider_name,
                            f"shared_account_tpm_soft_cap ({acct_tpm}+{est_tok}>{self.shared_account_tpm})",
                            wait_roll
                        )
                else:
                    eligible_wait_times = []

                    for _ in range(len(self.keys)):
                        idx = self._index % len(self.keys)
                        self._index += 1

                        if self._quarantined[idx]:
                            continue

                        if now < self._cooldown_until[idx]:
                            eligible_wait_times.append(self._cooldown_until[idx] - now)
                            continue

                        if self._in_flight[idx] >= self.max_in_flight_per_key:
                            eligible_wait_times.append(0.25)
                            continue

                        if len(self._req_timestamps[idx]) >= self.soft_rpm_per_key:
                            oldest_req = self._req_timestamps[idx][0]
                            eligible_wait_times.append((oldest_req + 60.0) - now)
                            continue

                        key_tpm = self._get_key_rolling_tpm(idx)
                        if key_tpm + est_tok > self.soft_tpm_per_key:
                            if self._token_ledger[idx]:
                                oldest_tok = self._token_ledger[idx][0]["timestamp"]
                                eligible_wait_times.append((oldest_tok + 60.0) - now)
                            continue

                        elapsed_since_last = now - self._last_used[idx]
                        wait_needed = self.min_interval_sec - elapsed_since_last
                        if wait_needed > 0:
                            eligible_wait_times.append(wait_needed)
                            continue

                        # Key is immediately eligible
                        lease_id = str(uuid.uuid4())
                        self._last_used[idx] = now
                        self._req_timestamps[idx].append(now)
                        token_record = {"id": lease_id, "timestamp": now, "tokens": est_tok}
                        self._token_ledger[idx].append(token_record)
                        self._active_reservations[lease_id] = {
                            "key_idx": idx,
                            "estimated": est_tok,
                            "reconciled": False
                        }
                        self._in_flight[idx] += 1
                        self._total_calls[idx] += 1

                        return KeyLease(
                            pool=self,
                            lease_id=lease_id,
                            key_index=idx,
                            credential=self.keys[idx],
                            estimated_tokens=est_tok,
                            reserved_at=now
                        )

                    soonest = min(eligible_wait_times) if eligible_wait_times else 30.0
                    remaining = max_wait_sec - total_waited
                    if remaining > 0.0 and soonest <= remaining:
                        wait_to_sleep = max(0.05, soonest)
                    else:
                        raise PoolExhaustedError(
                            self.provider_name,
                            f"all_{len(self.keys)}_keys_cooling_or_tpm_saturated",
                            max(0.5, soonest)
                        )

            if wait_to_sleep > 0.0:
                total_waited += wait_to_sleep
                await asyncio.sleep(wait_to_sleep)

    def _release_in_flight(self, key_idx: int, lease_id: Optional[str] = None):
        """Decrements in-flight concurrency count and cleans up reservation reference."""
        if 0 <= key_idx < len(self._in_flight):
            self._in_flight[key_idx] = max(0, self._in_flight[key_idx] - 1)
        if lease_id:
            self._active_reservations.pop(lease_id, None)

    def _reconcile_outcome(
        self,
        lease_id: str,
        key_index: int,
        actual_tokens: Optional[int] = None,
        rate_limited: bool = False,
        retry_after: Optional[float] = None,
        permanent_error: bool = False
    ):
        """Updates rolling ledger with actual tokens and cooldown state."""
        now = time.monotonic()
        if not (0 <= key_index < len(self.keys)):
            return

        if permanent_error:
            if retry_after is not None and retry_after > 0:
                self._cooldown_until[key_index] = max(self._cooldown_until[key_index], now + retry_after)
                print(f"[{self.provider_name}] Key #{key_index + 1} quota exhausted until reset window ({retry_after:.0f}s). Fast-switching.")
            else:
                self._quarantined[key_index] = True
                print(f"[{self.provider_name}] Key #{key_index + 1} permanently quarantined (credential invalid/revoked).")
            return

        if rate_limited:
            self._total_429s[key_index] += 1
            # Bounded exponential backoff with full jitter: d_k ~ U(0, min(d_max, d_0 * 2^attempts))
            if retry_after is not None and retry_after > 0:
                cooldown = max(2.0, float(retry_after))
            else:
                attempts = min(5, self._total_429s[key_index])
                base_backoff = min(30.0, 2.0 * (2 ** (attempts - 1)))
                jitter = random.uniform(0.5, 2.5)
                cooldown = max(5.0, base_backoff + jitter)
            self._cooldown_until[key_index] = max(self._cooldown_until[key_index], now + cooldown)
            print(f"[{self.provider_name}] Key #{key_index + 1} on cooldown for {cooldown:.1f}s (HTTP 429). Fast-switching.")

        if actual_tokens is not None:
            tok_q = self._token_ledger[key_index]
            for item in tok_q:
                if item["id"] == lease_id:
                    item["tokens"] = max(0, actual_tokens)
                    break

    # --- Backwards compatibility shims ---
    async def get_key(self) -> str:
        """Compatibility method for legacy single-string calls."""
        lease = await self.acquire_lease(estimated_tokens=1500, max_wait_sec=0.0)
        lease.release()
        return lease.credential if isinstance(lease.credential, str) else lease.credential[0]

    async def mark_rate_limited(self, key: str, cooldown_seconds: float = 30.0):
        """Compatibility method for legacy 429 reports."""
        async with self._lock:
            try:
                idx = self.keys.index(key)
                self._cooldown_until[idx] = max(self._cooldown_until[idx], time.monotonic() + cooldown_seconds)
                self._total_429s[idx] += 1
            except ValueError:
                pass


class CloudflareKeyPool(ProviderKeyPool):
    """Manages pairs of (api_token, account_id) for Cloudflare Workers AI."""
    def __init__(
        self,
        pairs: List[Tuple[str, str]],
        soft_rpm_per_key: int = 28,
        soft_tpm_per_key: int = 40000,
        shared_account_tpm: int = 120000,
        min_interval_sec: float = 1.0,
        max_in_flight_per_key: int = 2
    ):
        super().__init__(
            provider_name="Cloudflare",
            keys=pairs,
            soft_rpm_per_key=soft_rpm_per_key,
            soft_tpm_per_key=soft_tpm_per_key,
            shared_account_tpm=shared_account_tpm,
            min_interval_sec=min_interval_sec,
            max_in_flight_per_key=max_in_flight_per_key
        )

    async def get_pair(self) -> Tuple[str, str]:
        """Compatibility method returning next (api_token, account_id) tuple."""
        lease = await self.acquire_lease(estimated_tokens=1500, max_wait_sec=0.0)
        lease.release()
        return lease.credential

    async def mark_rate_limited(self, pair: tuple, cooldown_seconds: float = 30.0):
        async with self._lock:
            try:
                idx = self.keys.index(pair)
                self._cooldown_until[idx] = max(self._cooldown_until[idx], time.monotonic() + cooldown_seconds)
                self._total_429s[idx] += 1
            except ValueError:
                pass


class PremiumModelBudgetTracker:
    """
    Centrally tracks and enforces the exact 4-call-per-run budget for gemini-3.8-flash.
    Enforces stage eligibility, isolates state per run_id so concurrent or resumed runs
    never erase each other's accounting, and counts outbound attempts atomically.
    """
    ELIGIBLE_PREMIUM_STAGES = {
        "phase2_initial_plan",
        "phase6_final_plan",
        "phase75_quality_audit",
        "phase8_master_synthesis",
    }

    def __init__(self, max_calls_per_run: int = 4):
        self.max_calls_per_run = max_calls_per_run
        self._lock = asyncio.Lock()
        self.active_run_id: str = "default"
        self._run_states: Dict[str, Dict[str, Any]] = {
            "default": {"calls_used": 0, "claimed_stages": {}}
        }

    def _ensure_run_state(self, run_id: str) -> Dict[str, Any]:
        if run_id not in self._run_states:
            self._run_states[run_id] = {"calls_used": 0, "claimed_stages": {}}
        return self._run_states[run_id]

    @property
    def calls_used(self) -> int:
        return self._ensure_run_state(self.active_run_id)["calls_used"]

    @calls_used.setter
    def calls_used(self, value: int):
        self._ensure_run_state(self.active_run_id)["calls_used"] = value

    @property
    def claimed_stages(self) -> Dict[str, Dict[str, Any]]:
        return self._ensure_run_state(self.active_run_id)["claimed_stages"]

    def get_calls_used(self, run_id: Optional[str] = None) -> int:
        effective_run = run_id or self.active_run_id
        return self._ensure_run_state(effective_run)["calls_used"]

    def reset_for_run(self, run_id: str, force: bool = False):
        """
        Initializes or resets the budget counter for a specific run_id.
        Does NOT wipe any other concurrent run's state in _run_states.
        If force=False and run_id already has used slots, retains existing accounting.
        """
        state = self._ensure_run_state(run_id)
        if not force and state["calls_used"] > 0:
            self.active_run_id = run_id
            print(f"[PremiumBudgetTracker] Retaining active run '{run_id}' with {state['calls_used']} used slots.")
            return

        self.active_run_id = run_id
        self._run_states[run_id] = {"calls_used": 0, "claimed_stages": {}}
        print(f"[PremiumBudgetTracker] Reset budget for run '{run_id}': 0/{self.max_calls_per_run} slots used.")

    async def try_claim_gemini38_slot(self, stage_tag: str, run_id: Optional[str] = None) -> bool:
        """
        Atomically claims 1 of the 4 gemini-3.8-flash attempts immediately before outbound dispatch.
        Returns True if claimed, False if ineligible, already claimed for this stage, or budget exhausted.
        """
        if not stage_tag or stage_tag not in self.ELIGIBLE_PREMIUM_STAGES:
            return False

        async with self._lock:
            effective_run = run_id or self.active_run_id
            state = self._ensure_run_state(effective_run)
            stage_key = f"{effective_run}:{stage_tag}"

            if stage_key in state["claimed_stages"] or stage_tag in state["claimed_stages"]:
                # One outbound attempt per stage slot
                return False
            if state["calls_used"] >= self.max_calls_per_run:
                return False

            state["calls_used"] += 1
            slot_record = {
                "slot_number": state["calls_used"],
                "claimed_at": time.time(),
                "stage_tag": stage_tag,
                "run_id": effective_run
            }
            state["claimed_stages"][stage_key] = slot_record
            state["claimed_stages"][stage_tag] = slot_record
            print(f"[PremiumBudgetTracker] ✓ Claimed gemini-3.8-flash Slot #{state['calls_used']}/{self.max_calls_per_run} for stage '{stage_tag}' (run '{effective_run}').")
            return True


DEFAULT_PROVIDER_QUOTAS: Dict[str, Dict[str, Any]] = {
    "Gemini": {
        "soft_rpm_per_key": int(os.environ.get("COUNCIL_GEMINI_SOFT_RPM", "15")),
        "soft_tpm_per_key": int(os.environ.get("COUNCIL_GEMINI_SOFT_TPM", "800000")),
        "shared_account_tpm": int(os.environ.get("COUNCIL_GEMINI_SHARED_TPM", "2400000")),
        "min_interval_sec": float(os.environ.get("COUNCIL_GEMINI_MIN_INTERVAL", "0.8")),
        "max_in_flight_per_key": 1,
    },
    "Groq": {
        "soft_rpm_per_key": int(os.environ.get("COUNCIL_GROQ_SOFT_RPM", "25")),
        "soft_tpm_per_key": int(os.environ.get("COUNCIL_GROQ_SOFT_TPM", "30000")),
        "shared_account_tpm": int(os.environ.get("COUNCIL_GROQ_SHARED_TPM", "90000")),
        "min_interval_sec": float(os.environ.get("COUNCIL_GROQ_MIN_INTERVAL", "1.2")),
        "max_in_flight_per_key": 1,
    },
    "OpenRouter": {
        "soft_rpm_per_key": int(os.environ.get("COUNCIL_OPENROUTER_SOFT_RPM", "15")),
        "soft_tpm_per_key": int(os.environ.get("COUNCIL_OPENROUTER_SOFT_TPM", "35000")),
        "shared_account_tpm": int(os.environ.get("COUNCIL_OPENROUTER_SHARED_TPM", "90000")),
        "min_interval_sec": float(os.environ.get("COUNCIL_OPENROUTER_MIN_INTERVAL", "2.0")),
        "max_in_flight_per_key": 2,
    },
    "Cloudflare": {
        "soft_rpm_per_key": int(os.environ.get("COUNCIL_CLOUDFLARE_SOFT_RPM", "28")),
        "soft_tpm_per_key": int(os.environ.get("COUNCIL_CLOUDFLARE_SOFT_TPM", "40000")),
        "shared_account_tpm": int(os.environ.get("COUNCIL_CLOUDFLARE_SHARED_TPM", "120000")),
        "min_interval_sec": float(os.environ.get("COUNCIL_CLOUDFLARE_MIN_INTERVAL", "1.0")),
        "max_in_flight_per_key": 2,
    },
}


def _env_flag(name: str, default: bool = False) -> bool:
    """Reads a boolean environment flag with a safe default."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class MultiProviderKeyRotator:
    """Central registry and configuration manager for all provider key pools."""
    def __init__(self):
        groq_soft_rpm = int(os.environ.get("COUNCIL_GROQ_SOFT_RPM", "25"))
        groq_soft_tpm = int(os.environ.get("COUNCIL_GROQ_SOFT_TPM", "30000"))
        groq_shared_tpm = int(os.environ.get("COUNCIL_GROQ_SHARED_TPM", "90000"))

        gemini_soft_rpm = int(os.environ.get("COUNCIL_GEMINI_SOFT_RPM", "15"))
        gemini_soft_tpm = int(os.environ.get("COUNCIL_GEMINI_SOFT_TPM", "800000"))
        gemini_shared_tpm = int(os.environ.get("COUNCIL_GEMINI_SHARED_TPM", "2400000"))

        openrouter_soft_rpm = int(os.environ.get("COUNCIL_OPENROUTER_SOFT_RPM", "25"))
        openrouter_soft_tpm = int(os.environ.get("COUNCIL_OPENROUTER_SOFT_TPM", "120000"))
        openrouter_shared_tpm = int(os.environ.get("COUNCIL_OPENROUTER_SHARED_TPM", "360000"))

        cloudflare_soft_rpm = int(os.environ.get("COUNCIL_CLOUDFLARE_SOFT_RPM", "28"))
        cloudflare_soft_tpm = int(os.environ.get("COUNCIL_CLOUDFLARE_SOFT_TPM", "40000"))
        cloudflare_shared_tpm = int(os.environ.get("COUNCIL_CLOUDFLARE_SHARED_TPM", "120000"))

        # Keys from the same provider project share server-side quota. Default to safe shared
        # accounting; operators with genuinely distinct accounts can opt into independent pools.
        groq_independent = _env_flag("COUNCIL_GROQ_INDEPENDENT_ACCOUNTS", False)
        gemini_independent = _env_flag("COUNCIL_GEMINI_INDEPENDENT_ACCOUNTS", False)
        openrouter_independent = _env_flag("COUNCIL_OPENROUTER_INDEPENDENT_ACCOUNTS", False)

        self.groq_pool = ProviderKeyPool(
            "Groq",
            self._collect_keys("GROQ_API_KEY"),
            soft_rpm_per_key=groq_soft_rpm,
            soft_tpm_per_key=groq_soft_tpm,
            shared_account_tpm=groq_shared_tpm,
            min_interval_sec=0.3,
            max_in_flight_per_key=2,
            keys_are_independent_accounts=groq_independent
        )
        self.gemini_pool = ProviderKeyPool(
            "Gemini",
            self._collect_keys("GEMINI_API_KEY"),
            soft_rpm_per_key=gemini_soft_rpm,
            soft_tpm_per_key=gemini_soft_tpm,
            shared_account_tpm=gemini_shared_tpm,
            min_interval_sec=0.5,
            max_in_flight_per_key=2,
            keys_are_independent_accounts=gemini_independent
        )
        self.openrouter_pool = ProviderKeyPool(
            "OpenRouter",
            self._collect_keys("OPENROUTER_API_KEY"),
            soft_rpm_per_key=openrouter_soft_rpm,
            soft_tpm_per_key=openrouter_soft_tpm,
            shared_account_tpm=openrouter_shared_tpm,
            min_interval_sec=0.2,
            max_in_flight_per_key=3,
            keys_are_independent_accounts=openrouter_independent
        )
        self.cloudflare_pool = CloudflareKeyPool(
            self._collect_cloudflare_pairs(),
            soft_rpm_per_key=cloudflare_soft_rpm,
            soft_tpm_per_key=cloudflare_soft_tpm,
            shared_account_tpm=cloudflare_shared_tpm,
            min_interval_sec=1.0,
            max_in_flight_per_key=2
        )
        self.siliconflow_pool = ProviderKeyPool(
            "SiliconFlow",
            self._collect_keys("SILICONFLOW_API_KEY")
        )
        self.huggingface_pool = ProviderKeyPool(
            "HuggingFace",
            self._collect_keys("HUGGINGFACE_API_KEY")
        )

        self.budget_tracker = PremiumModelBudgetTracker(max_calls_per_run=4)

    def _collect_keys(self, prefix: str) -> List[str]:
        keys = []
        seen = set()
        v0 = os.environ.get(prefix)
        if v0 and v0.strip():
            c = v0.strip()
            seen.add(c)
            keys.append(c)
        for i in range(1, 20):
            var_name = f"{prefix}_{i}"
            val = os.environ.get(var_name)
            if val and val.strip():
                c = val.strip()
                if c not in seen:
                    seen.add(c)
                    keys.append(c)
        return keys

    def _collect_cloudflare_pairs(self) -> List[Tuple[str, str]]:
        pairs = []
        seen = set()
        k_single = os.environ.get("CLOUDFLARE_API_KEY") or os.environ.get("CLOUDFLARE_API_TOKEN")
        a_single = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        if k_single and a_single and k_single.strip() and a_single.strip():
            pair = (k_single.strip(), a_single.strip())
            seen.add(pair)
            pairs.append(pair)

        for i in range(1, 10):
            k = os.environ.get(f"CLOUDFLARE_API_KEY_{i}") or os.environ.get(f"CLOUDFLARE_API_TOKEN_{i}")
            a = os.environ.get(f"CLOUDFLARE_ACCOUNT_ID_{i}")
            if k and a and k.strip() and a.strip():
                pair = (k.strip(), a.strip())
                if pair not in seen:
                    seen.add(pair)
                    pairs.append(pair)
        return pairs

    def reset_for_run(self, run_id: str, force: bool = True):
        self.budget_tracker.reset_for_run(run_id, force=force)

    async def try_claim_gemini38_slot(self, stage_tag: str, run_id: Optional[str] = None) -> bool:
        return await self.budget_tracker.try_claim_gemini38_slot(stage_tag, run_id=run_id)

    def print_status(self):
        print("=== Multi-Provider Key Pool Status ===")
        print(f"• Groq:        {self.groq_pool.total_keys} active keys (Soft RPM: {self.groq_pool.soft_rpm_per_key}, TPM: {self.groq_pool.soft_tpm_per_key})")
        print(f"• Gemini:      {self.gemini_pool.total_keys} active keys (Soft RPM: {self.gemini_pool.soft_rpm_per_key}, TPM: {self.gemini_pool.soft_tpm_per_key})")
        print(f"• OpenRouter:  {self.openrouter_pool.total_keys} active keys (Soft RPM: {self.openrouter_pool.soft_rpm_per_key})")
        print(f"• Cloudflare:  {self.cloudflare_pool.total_keys} active accounts/keys (Soft RPM: {self.cloudflare_pool.soft_rpm_per_key})")
        print(f"• Gemini 3.8:  {self.budget_tracker.calls_used}/{self.budget_tracker.max_calls_per_run} premium stage slots used")
        print("=======================================")


# Global instance
key_rotator = MultiProviderKeyRotator()
