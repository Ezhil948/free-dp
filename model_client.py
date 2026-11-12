import os
import sys
import re
import time
import json
import asyncio
from typing import List, Dict, Any, Optional, Tuple
import openai
from openai import AsyncOpenAI
from key_rotator import key_rotator, PoolExhaustedError, KeyLease

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


class TruncatedResponseError(RuntimeError):
    """Raised when an LLM completion was truncated by finish_reason == 'length'."""
    pass


class ClientRequestError(RuntimeError):
    """Raised on non-retriable 400 Bad Request client errors."""
    pass


def estimate_messages_tokens(messages: List[Dict[str, str]], max_tokens: int = 2500) -> int:
    """Estimates outbound + completion tokens based on 3.5 characters per token."""
    char_count = sum(len(str(m.get("content", ""))) for m in messages if isinstance(m, dict))
    prompt_tokens = max(10, int(char_count / 3.5))
    return max(100, prompt_tokens + max(50, max_tokens))


PREMIUM_MODEL = os.environ.get("COUNCIL_PREMIUM_MODEL", "gemini-2.5-flash")
GEMINI_LEADER_FALLBACK = os.environ.get("COUNCIL_GEMINI_LEADER_FALLBACK", "gemini-flash-lite-latest")
GEMINI_PRIMARY_MODEL = os.environ.get("COUNCIL_GEMINI_PRIMARY_MODEL", "gemini-flash-lite-latest")
GEMINI_SECONDARY_MODEL = os.environ.get("COUNCIL_GEMINI_SECONDARY_MODEL", "gemini-2.5-flash")
GEMINI_FALLBACK_MODEL = GEMINI_PRIMARY_MODEL
GEMINI_FAST_MODEL = GEMINI_PRIMARY_MODEL
GROQ_WORKER_MODEL = os.environ.get("COUNCIL_WORKER_MODEL", "qwen/qwen3.8-27b")
GROQ_HEAVY_MODEL = os.environ.get("COUNCIL_GROQ_HEAVY_MODEL", "openai/gpt-oss-120b")
GROQ_MEDIUM_MODEL = os.environ.get("COUNCIL_GROQ_MEDIUM_MODEL", "openai/gpt-oss-20b")
OPENROUTER_MODEL = os.environ.get("COUNCIL_OPENROUTER_MODEL", "nvidia/nemotron-3.5-lightning:free")
CLOUDFLARE_MODEL = os.environ.get("COUNCIL_CLOUDFLARE_MODEL", "@cf/meta/llama-3.2-3b-instruct")

# Structured Tier Routing Table (Gemini 3.1 Flash-Lite Primary with 10 Keys Pool)
TIER_ROUTES: Dict[str, List[Dict[str, Any]]] = {
    "leader_premium": [
        {"provider": "Gemini", "model": "gemini-3.1-flash-lite", "timeout": 45.0},
        {"provider": "Gemini", "model": "gemini-flash-lite-latest", "timeout": 45.0},
        {"provider": "Groq", "model": GROQ_HEAVY_MODEL, "timeout": 30.0},
        {"provider": "Groq", "model": GROQ_WORKER_MODEL, "timeout": 25.0},
        {"provider": "OpenRouter", "model": OPENROUTER_MODEL, "timeout": 45.0},
    ],
    "leader_standard": [
        {"provider": "Gemini", "model": "gemini-3.1-flash-lite", "timeout": 45.0},
        {"provider": "Gemini", "model": "gemini-flash-lite-latest", "timeout": 45.0},
        {"provider": "Groq", "model": GROQ_HEAVY_MODEL, "timeout": 30.0},
        {"provider": "Groq", "model": GROQ_WORKER_MODEL, "timeout": 25.0},
        {"provider": "OpenRouter", "model": OPENROUTER_MODEL, "timeout": 45.0},
    ],
    "council_member": [
        {"provider": "Gemini", "model": "gemini-3.1-flash-lite", "timeout": 45.0},
        {"provider": "Gemini", "model": "gemini-flash-lite-latest", "timeout": 45.0},
        {"provider": "Groq", "model": GROQ_WORKER_MODEL, "timeout": 25.0},
        {"provider": "Groq", "model": GROQ_MEDIUM_MODEL, "timeout": 25.0},
        {"provider": "OpenRouter", "model": OPENROUTER_MODEL, "timeout": 40.0},
    ],
    "worker_empirical": [
        {"provider": "Gemini", "model": "gemini-3.1-flash-lite", "timeout": 45.0},
        {"provider": "Gemini", "model": "gemini-flash-lite-latest", "timeout": 45.0},
        {"provider": "Groq", "model": GROQ_WORKER_MODEL, "timeout": 25.0},
        {"provider": "Groq", "model": GROQ_MEDIUM_MODEL, "timeout": 25.0},
        {"provider": "OpenRouter", "model": OPENROUTER_MODEL, "timeout": 40.0},
    ],
    "worker_analytical": [
        {"provider": "Gemini", "model": "gemini-3.1-flash-lite", "timeout": 45.0},
        {"provider": "Gemini", "model": "gemini-flash-lite-latest", "timeout": 45.0},
        {"provider": "Groq", "model": GROQ_WORKER_MODEL, "timeout": 25.0},
        {"provider": "Groq", "model": GROQ_MEDIUM_MODEL, "timeout": 25.0},
        {"provider": "OpenRouter", "model": OPENROUTER_MODEL, "timeout": 40.0},
    ],
}


class ModelCaller:
    """
    Tier-based Model Client with:
    - Lease-guarded atomic credential acquisition
    - Non-blocking fast-switch on PoolExhaustedError (<10ms)
    - 4-call run budget enforcement for gemini-3.8-flash at outbound boundary
    - Explicit max_retries=0 to disable hidden SDK retries
    - Hard wall-clock overall deadline enforcement across route chains
    - Response truncation detection & typed error handling
    - Full backward-compatibility preserving exact legacy positional arguments
    """

    def __init__(
        self,
        default_leader_model: str = GEMINI_FALLBACK_MODEL,
        default_member_model: str = GROQ_WORKER_MODEL,
        default_worker_model: str = GROQ_WORKER_MODEL,
        backup_model: str = GEMINI_FALLBACK_MODEL
    ):
        self.leader_model = default_leader_model
        self.member_model = default_member_model
        self.worker_model = default_worker_model
        self.backup_model = backup_model
        self.call_telemetry_log: List[Dict[str, Any]] = []
        self._unavailable_models: set = set()
        self._client_cache: Dict[Any, AsyncOpenAI] = {}

    def _get_client(self, provider: str, credential: Any, timeout: float) -> AsyncOpenAI:
        """Returns a cached AsyncOpenAI client to reuse persistent HTTP/2 connections and prevent socket exhaustion."""
        p = provider.lower()
        cache_key = (p, credential if isinstance(credential, str) else tuple(credential), timeout)
        if cache_key not in self._client_cache:
            if "gemini" in p:
                client = AsyncOpenAI(
                    api_key=credential,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                    timeout=timeout,
                    max_retries=0
                )
            elif "groq" in p:
                client = AsyncOpenAI(
                    api_key=credential,
                    base_url="https://api.groq.com/openai/v1",
                    timeout=timeout,
                    max_retries=0
                )
            elif "cloudflare" in p:
                api_token, account_id = credential
                base_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1"
                client = AsyncOpenAI(
                    api_key=api_token,
                    base_url=base_url,
                    timeout=timeout,
                    max_retries=0
                )
            elif "openrouter" in p:
                client = AsyncOpenAI(
                    api_key=credential,
                    base_url="https://openrouter.ai/api/v1",
                    timeout=timeout,
                    max_retries=0
                )
            elif "siliconflow" in p:
                client = AsyncOpenAI(
                    api_key=credential,
                    base_url="https://api.siliconflow.cn/v1",
                    timeout=timeout,
                    max_retries=0
                )
            elif "huggingface" in p:
                client = AsyncOpenAI(
                    api_key=credential,
                    base_url="https://api-inference.huggingface.co/v1",
                    timeout=timeout,
                    max_retries=0
                )
            else:
                client = AsyncOpenAI(api_key=credential, timeout=timeout, max_retries=0)
            self._client_cache[cache_key] = client
        return self._client_cache[cache_key]

    def _get_pool_for_provider(self, provider_name: str):
        """Maps provider name string to corresponding key pool."""
        p = provider_name.lower()
        if "gemini" in p or "google" in p:
            return key_rotator.gemini_pool
        elif "groq" in p:
            return key_rotator.groq_pool
        elif "cloudflare" in p:
            return key_rotator.cloudflare_pool
        elif "openrouter" in p:
            return key_rotator.openrouter_pool
        elif "siliconflow" in p:
            return key_rotator.siliconflow_pool
        elif "huggingface" in p:
            return key_rotator.huggingface_pool
        else:
            raise ValueError(f"Unsupported model provider: '{provider_name}'")

    @staticmethod
    def _looks_structurally_truncated(content: str) -> bool:
        """Detects unfinished code/LaTeX structures that indicate a hard max_tokens cut."""
        text = content.rstrip()
        if not text:
            return True
        if text.count("```") % 2 != 0:
            return True
        if text.count("$$") % 2 != 0:
            return True

        begins = re.findall(r"\\begin\{([a-zA-Z*]+)\}", text)
        ends = re.findall(r"\\end\{([a-zA-Z*]+)\}", text)
        for env in set(begins):
            if begins.count(env) != ends.count(env):
                return True

        # A response ending on a binary operator/opening delimiter was cut mid-expression.
        if re.search(r"(?:\\[a-zA-Z]+\{?|[-+*/=,(])\s*$", text):
            return True
        return False

    async def _execute_single_http_attempt(
        self,
        provider: str,
        model: str,
        credential: Any,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
        timeout: float,
        first_content_timeout: float = 8.0
    ) -> Tuple[str, Optional[int], str]:
        """
        Executes an HTTP attempt via AsyncOpenAI client with streaming (stream=True).
        Enforces a Time-To-First-Content (TTFC) deadline (default 8.0s) for Gemini.
        If zero content chunks arrive within TTFC, aborts early to fast-failover across routes.
        """
        client = self._get_client(provider, credential, timeout)

        effective_max_tokens = max_tokens
        if "qwen" in model.lower():
            # Groq's free TPM ceiling motivated the old hardcoded 950-token cap, which truncated
            # multi-page derivations and code mid-line. Keep the guard configurable instead.
            try:
                qwen_cap = int(os.environ.get("COUNCIL_QWEN_MAX_TOKENS", "4096"))
            except ValueError:
                qwen_cap = 4096
            effective_max_tokens = min(max_tokens, max(256, qwen_cap))

        # For Gemini providers, use streaming with TTFC deadline
        is_gemini = "gemini" in provider.lower() or "gemini" in model.lower()

        if is_gemini:
            collected_chunks: List[str] = []
            finish_reason = "stop"
            used_tokens: Optional[int] = None

            try:
                stream_resp = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=effective_max_tokens,
                    temperature=temperature,
                    stream=True
                )
            except (openai.APIConnectionError, ConnectionError):
                self._client_cache.clear()
                fresh_client = self._get_client(provider, credential, timeout)
                stream_resp = await fresh_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=effective_max_tokens,
                    temperature=temperature,
                    stream=True
                )

            # Stream chunk processing with TTFC guard
            stream_iter = stream_resp.__aiter__()
            first_chunk_received = False
            start_t = time.monotonic()

            try:
                while True:
                    cur_wait = first_content_timeout if not first_chunk_received else timeout
                    try:
                        chunk = await asyncio.wait_for(stream_iter.__anext__(), timeout=cur_wait)
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        if not first_chunk_received:
                            raise TimeoutError(f"TTFC_TIMEOUT: No content chunk arrived from {provider} ({model}) within {first_content_timeout}s.")
                        else:
                            raise TimeoutError(f"STREAM_IDLE_TIMEOUT: Stream stalled after first content on {provider} ({model}).")

                    if chunk.choices and len(chunk.choices) > 0:
                        choice = chunk.choices[0]
                        if getattr(choice, "finish_reason", None):
                            finish_reason = choice.finish_reason
                        delta = getattr(choice, "delta", None)
                        if delta:
                            content_delta = getattr(delta, "content", None) or ""
                            if not content_delta and hasattr(delta, "reasoning") and delta.reasoning:
                                content_delta = delta.reasoning
                            if content_delta:
                                if not first_chunk_received:
                                    first_chunk_received = True
                                    ttfc_ms = (time.monotonic() - start_t) * 1000
                                collected_chunks.append(content_delta)

                    if hasattr(chunk, "usage") and chunk.usage:
                        tot = getattr(chunk.usage, "total_tokens", None)
                        if tot:
                            used_tokens = int(tot)

            finally:
                if hasattr(stream_resp, "response") and hasattr(stream_resp.response, "aclose"):
                    try:
                        await stream_resp.response.aclose()
                    except Exception:
                        pass

            final_content = "".join(collected_chunks).strip()
            return final_content, used_tokens, finish_reason

        # Standard non-streaming path for non-Gemini providers (Groq, OpenRouter, Cloudflare)
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=effective_max_tokens,
                temperature=temperature
            )
        except (openai.APIConnectionError, ConnectionError):
            self._client_cache.clear()
            fresh_client = self._get_client(provider, credential, timeout)
            resp = await fresh_client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=effective_max_tokens,
                temperature=temperature
            )

        choice = resp.choices[0]
        finish_reason = getattr(choice, "finish_reason", "stop") or "stop"

        msg = choice.message
        content = msg.content or ""
        if not content and hasattr(msg, "reasoning") and msg.reasoning:
            content = msg.reasoning

        used_tokens: Optional[int] = None
        if hasattr(resp, "usage") and resp.usage:
            tot = getattr(resp.usage, "total_tokens", None)
            if tot is not None and tot > 0:
                used_tokens = int(tot)

        return content.strip(), used_tokens, finish_reason

    async def call_by_tier(
        self,
        tier: str,
        messages: List[Dict[str, str]],
        *,
        stage_tag: Optional[str] = None,
        max_tokens: int = 2500,
        temperature: float = 0.3,
        overall_deadline: float = 120.0,
        run_id: Optional[str] = None,
        allow_truncation: bool = False
    ) -> str:
        """
        Dispatches request through prioritized routes for the given tier.
        Enforces:
        - Outer asyncio.timeout covering the entire logical call
        - Safe lease lifecycle: lease acquired, enter async with lease, then claim premium slot
        - Clean reservation wipe if claim fails
        - Rejection of truncated responses if allow_truncation is False
        """
        async with asyncio.timeout(overall_deadline):
            routes = TIER_ROUTES.get(tier, TIER_ROUTES["council_member"])
            deadline = time.monotonic() + overall_deadline
            est_tokens = estimate_messages_tokens(messages, max_tokens=max_tokens)

            errors_log: List[str] = []
            fallback_chain_tried: List[str] = []

            while time.monotonic() < deadline - 0.5:
                for route_idx, route in enumerate(routes):
                    now = time.monotonic()
                    time_left = deadline - now
                    if time_left <= 0.5:
                        print(f"[ModelCaller] Overall wall-clock deadline nearly expired ({time_left:.2f}s left).")
                        break

                    provider = route["provider"]
                    model = route["model"]
                    is_premium = bool(route.get("is_premium_slot", False)) or ("gemini" in model.lower() and "3.8" in model)

                    if (provider.lower(), model) in self._unavailable_models:
                        print(f"[ModelCaller] Skipping unavailable route {provider} ({model}).")
                        continue

                    # Pre-check stage eligibility
                    if is_premium:
                        if not stage_tag or stage_tag not in key_rotator.budget_tracker.ELIGIBLE_PREMIUM_STAGES:
                            print(f"[ModelCaller] Skipping {model}: ineligible stage '{stage_tag}'. Fast-switching to fallback.")
                            continue
                        if key_rotator.budget_tracker.get_calls_used(run_id) >= key_rotator.budget_tracker.max_calls_per_run:
                            print(f"[ModelCaller] Budget full (4/4 used) for {model}. Fast-switching to fallback.")
                            continue

                    # Groq hard ceiling: Groq fails with 413 on requests exceeding 8,000 TPM
                    if provider.lower() == "groq" and est_tokens > 7000:
                        print(f"[ModelCaller] Skipping {provider} ({model}): estimated tokens {est_tokens} exceeds Groq 8000 TPM limit. Fast-switching...")
                        continue

                    fallback_chain_tried.append(f"{provider}:{model}")

                    try:
                        pool = self._get_pool_for_provider(provider)
                    except ValueError as ve:
                        errors_log.append(str(ve))
                        continue

                    # Atomic lease acquisition (allow wait up to 3.5s for keys that are cooling or TPM slots clearing)
                    try:
                        wait_budget = min(3.5, max(0.2, time_left - 3.0)) if time_left > 5.0 else 0.0
                        lease = await pool.acquire_lease(
                            estimated_tokens=est_tokens,
                            max_wait_sec=wait_budget
                        )
                    except PoolExhaustedError as pe:
                        print(f"[ModelCaller] {pe.reason}. Fast-switching from {provider} ({model}) in <10ms...")
                        errors_log.append(f"{provider}:{model} -> {pe}")
                        continue
                    except Exception as e:
                        print(f"[ModelCaller] Lease acquire error for {provider}: {e}. Switching...")
                        errors_log.append(f"{provider}:{model} -> {e}")
                        continue

                    # Codx Fix: Wrap inside lease context IMMEDIATELY to prevent cancellation leaks
                    try:
                        async with lease:
                            if is_premium:
                                claimed = await key_rotator.try_claim_gemini38_slot(stage_tag, run_id=run_id)
                                if not claimed:
                                    # Wipe provisional reservation since no request was dispatched
                                    lease.record_outcome(actual_tokens=0)
                                    print(f"[ModelCaller] Failed to claim premium slot for {model} (stage '{stage_tag}'). Fast-switching...")
                                    continue

                            # Calculate attempt timeout dynamically right before dispatch
                            now = time.monotonic()
                            per_attempt_timeout = min(route["timeout"], max(1.0, deadline - now - 0.5))

                            t0 = time.monotonic()
                            content, actual_tokens, finish_reason = await asyncio.wait_for(
                                self._execute_single_http_attempt(
                                    provider=provider,
                                    model=model,
                                    credential=lease.credential,
                                    messages=messages,
                                    max_tokens=max_tokens,
                                    temperature=temperature,
                                    timeout=per_attempt_timeout
                                ),
                                timeout=per_attempt_timeout
                            )
                            elapsed = time.monotonic() - t0

                            # Reject structurally broken completions (unclosed code fences,
                            # unbalanced display math, unfinished \begin environments) instead of
                            # accepting a long fragment. Valid partial JSON may still be repaired.
                            if finish_reason == "length" and not allow_truncation:
                                test_parse = self.extract_json(content)
                                structurally_cut = self._looks_structurally_truncated(content)
                                if structurally_cut:
                                    print(f"[ModelCaller] Warning: {provider} ({model}) truncated mid-structure at max_tokens ({max_tokens}). Failing over for full completion...")
                                    lease.record_outcome(actual_tokens=actual_tokens)
                                    errors_log.append(f"{provider}:{model} structurally truncated (finish_reason=length)")
                                    continue
                                if not test_parse.get("_parse_error") or len(content.strip()) >= 500:
                                    print(f"[ModelCaller] Notice: {provider} ({model}) reached max_tokens ({max_tokens}), but response ({len(content)} chars) is substantial or repaired. Accepting.")
                                else:
                                    print(f"[ModelCaller] Warning: {provider} ({model}) truncated at max_tokens ({max_tokens}). Failing over for full completion...")
                                    lease.record_outcome(actual_tokens=actual_tokens)
                                    errors_log.append(f"{provider}:{model} truncated (finish_reason=length)")
                                    continue

                            if content:
                                lease.record_outcome(actual_tokens=actual_tokens)
                                self.call_telemetry_log.append({
                                    "run_id": run_id or "default",
                                    "stage_tag": stage_tag or "unspecified",
                                    "tier": tier,
                                    "provider_used": provider,
                                    "model_used": model,
                                    "is_premium_slot": is_premium,
                                    "tokens_est": est_tokens,
                                    "actual_tokens": actual_tokens or est_tokens,
                                    "latency_ms": round(elapsed * 1000, 1),
                                    "fallback_chain_tried": list(fallback_chain_tried),
                                })
                                print(f"[ModelCaller] ✓ Success: [{tier}] {provider} ({model}) in {elapsed:.2f}s ({actual_tokens or est_tokens} tok, finish: {finish_reason}).")
                                return content
                            else:
                                print(f"[ModelCaller] Empty response from {provider} ({model}). Fast-switching...")
                                errors_log.append(f"{provider}:{model} returned empty response")

                    except openai.BadRequestError as bre:
                        # Treat malformed/oversized requests as route-local: mark this route
                        # unavailable for the run and continue the fallback chain.
                        self._unavailable_models.add((provider.lower(), model))
                        lease.record_outcome(actual_tokens=0)
                        print(f"[ModelCaller] Bad Request (400) on {provider} ({model}): {bre}. Caching route as unavailable and switching...")
                        errors_log.append(f"{provider}:{model} 400 -> {bre}")
                        continue

                    except openai.NotFoundError as nfe:
                        # Model ID unavailable on this provider - cache as unavailable for run
                        self._unavailable_models.add((provider.lower(), model))
                        lease.record_outcome(actual_tokens=0)
                        print(f"[ModelCaller] Model not found (404) on {provider} ({model}): {nfe}. Caching route as unavailable.")
                        errors_log.append(f"{provider}:{model} 404 -> {nfe}")

                    except openai.AuthenticationError as ae:
                        # Permanent credential invalidation
                        lease.record_outcome(permanent_error=True)
                        print(f"[ModelCaller] Auth error on {provider}: {ae}. Key quarantined.")
                        errors_log.append(f"{provider}:{model} auth error -> {ae}")

                    except openai.RateLimitError as rle:
                        rle_str = str(rle).lower()
                        retry_after = 15.0
                        if hasattr(rle, "response") and rle.response and rle.response.headers:
                            raw_ra = rle.response.headers.get("retry-after")
                            if raw_ra:
                                try:
                                    retry_after = float(raw_ra)
                                except ValueError:
                                    pass

                        # Extract embedded retry delay or reset window if specified in JSON payload
                        import re
                        m_delay = re.search(r'retrydelay[\'":\s]+(\d+)', rle_str)
                        if m_delay:
                            try:
                                retry_after = max(retry_after, float(m_delay.group(1)))
                            except ValueError:
                                pass
                        m_h = re.search(r'retry in (\d+)h(\d+)m', rle_str)
                        if m_h:
                            retry_after = max(retry_after, float(m_h.group(1)) * 3600.0 + float(m_h.group(2)) * 60.0)
                        m_m = re.search(r'retry in (\d+)m', rle_str)
                        if m_m:
                            retry_after = max(retry_after, float(m_m.group(1)) * 60.0)

                        # Accurate classification of permanent daily exhaustion vs transient RPM throttles
                        is_perm = False
                        if provider.lower() == "cloudflare":
                            is_perm = "daily free allocation" in rle_str or "10,000 neurons" in rle_str
                        elif provider.lower() == "openrouter":
                            is_perm = "free-models-per-day" in rle_str or "limit_source" in rle_str
                        elif provider.lower() == "gemini":
                            # Matches "Generate content requests per day limit exceeded" or "requests per day" or explicit delay > 5m
                            is_perm = (
                                "requests per day" in rle_str
                                or "generaterequestsperday" in rle_str
                                or "generate content requests per day" in rle_str
                                or "generatecontent requests per day" in rle_str
                                or "daily limit exceeded" in rle_str
                                or retry_after > 300.0
                            )

                        # NEVER cache Gemini models as unavailable at provider level because pool has independent keys with rolling RPMs
                        if is_perm and provider.lower() not in ("gemini",):
                            self._unavailable_models.add((provider.lower(), model))
                            print(f"[ModelCaller] Daily quota exhausted for {provider} ({model}). Caching route as unavailable.")

                        lease.record_outcome(rate_limited=True, retry_after=retry_after, permanent_error=is_perm)
                        print(f"[ModelCaller] RateLimitError on {provider} ({model}): Retry-After={retry_after:.1f}s (perm={is_perm}). Fast-switching...")
                        errors_log.append(f"{provider}:{model} 429 -> {rle}")

                    except Exception as e:
                        err_str = str(e).lower()
                        elapsed = time.monotonic() - t0
                        is_429 = "429" in err_str or "rate limit" in err_str or "resource_exhausted" in err_str
                        is_invalid = "invalid api key" in err_str or "api_key_invalid" in err_str or "revoked" in err_str or "daily free allocation" in err_str
                        is_404 = "404" in err_str or "model_not_found" in err_str or "does not exist" in err_str
                        if is_404:
                            self._unavailable_models.add((provider.lower(), model))
                        if "connection" in err_str or "connect" in err_str:
                            self._client_cache.clear()

                        lease.record_outcome(
                            rate_limited=is_429,
                            permanent_error=is_invalid
                        )
                        print(f"[ModelCaller] Route {provider} ({model}) failed in {elapsed:.2f}s: {e}. Fast-switching...")
                        errors_log.append(f"{provider}:{model} -> {e}")

                # End of a route sweep across all available providers.
                # If still within deadline, pause briefly so cooling keys or clearing in-flight slots become eligible
                now = time.monotonic()
                if now < deadline - 0.8:
                    pause_sec = min(1.5, max(0.2, deadline - now - 0.5))
                    await asyncio.sleep(pause_sec)

            summary_err = "; ".join(errors_log)
            raise RuntimeError(f"All routes exhausted for tier '{tier}' within deadline ({overall_deadline}s). Errors: {summary_err}")

    def get_telemetry_markdown_table(self, run_id: Optional[str] = None) -> str:
        """Generates a Markdown summary table of all LLM calls for Phase 8 Section 5."""
        entries = [
            e for e in self.call_telemetry_log
            if run_id is None or e.get("run_id") == run_id or e.get("run_id") == "default"
        ]
        if not entries:
            return "_No model telemetry entries recorded for this run._"

        lines = [
            "| # | Stage Tag | Tier | Provider | Model | Premium Slot | Tokens | Latency (ms) | Fallback Chain Tried |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
        ]
        for idx, e in enumerate(entries, start=1):
            chain_str = " -> ".join(e.get("fallback_chain_tried", []))
            prem_str = "YES" if e.get("is_premium_slot") else "No"
            lines.append(
                f"| {idx} | `{e.get('stage_tag')}` | `{e.get('tier')}` | `{e.get('provider_used')}` | "
                f"`{e.get('model_used')}` | {prem_str} | {e.get('actual_tokens')} | {e.get('latency_ms')} | `{chain_str}` |"
            )
        return "\n".join(lines)

    # --- Backwards compatibility methods with PRESERVED POSITIONAL ARGUMENTS ---
    async def call_groq(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 2500,
        temperature: float = 0.4,
        max_retries: int = 2,
        *,
        stage_tag: Optional[str] = None
    ) -> str:
        return await self.call_by_tier(
            "council_member",
            messages,
            stage_tag=stage_tag,
            max_tokens=max_tokens,
            temperature=temperature
        )

    async def call_gemini(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 6000,
        temperature: float = 0.3,
        max_retries: int = 2,
        *,
        stage_tag: Optional[str] = None
    ) -> str:
        tier = "leader_premium" if "3.8" in model else "leader_standard"
        return await self.call_by_tier(
            tier,
            messages,
            stage_tag=stage_tag,
            max_tokens=max_tokens,
            temperature=temperature
        )

    async def call_cloudflare(
        self,
        model: str = "@cf/meta/llama-3.1-70b-instruct",
        messages: List[Dict[str, str]] = None,
        max_tokens: int = 2500,
        temperature: float = 0.4,
        max_retries: int = 2,
        *,
        stage_tag: Optional[str] = None
    ) -> str:
        msgs = messages or []
        return await self.call_by_tier(
            "council_member",
            msgs,
            stage_tag=stage_tag,
            max_tokens=max_tokens,
            temperature=temperature
        )

    async def call_openrouter(
        self,
        model: str = "deepseek/deepseek-chat",
        messages: List[Dict[str, str]] = None,
        max_tokens: int = 2500,
        temperature: float = 0.4,
        max_retries: int = 2,
        *,
        stage_tag: Optional[str] = None
    ) -> str:
        msgs = messages or []
        return await self.call_by_tier(
            "council_member",
            msgs,
            stage_tag=stage_tag,
            max_tokens=max_tokens,
            temperature=temperature
        )

    async def call_model(
        self,
        model: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        max_tokens: int = 2500,
        temperature: float = 0.4,
        provider: str = "",
        *,
        stage_tag: Optional[str] = None,
        overall_deadline: float = 75.0
    ) -> str:
        """
        Generic dispatcher preserving legacy positional parameter order:
        call_model(model, messages, max_tokens, temperature, provider)
        """
        msgs = messages or []
        p_lower = (provider or "").lower()
        target_model = (model or "").lower()

        # If provider is explicitly specified by caller, prioritize that tier/route
        if "cloudflare" in p_lower:
            tier = "council_member"
        elif "openrouter" in p_lower:
            tier = "council_member"
        elif "gemini" in p_lower or "google" in p_lower:
            tier = "leader_premium" if "3.8" in target_model else "leader_standard"
        elif "3.8" in target_model:
            tier = "leader_premium"
        elif "worker" in target_model or "empirical" in target_model:
            tier = "worker_empirical"
        else:
            tier = "council_member"

        return await self.call_by_tier(
            tier=tier,
            messages=msgs,
            stage_tag=stage_tag,
            max_tokens=max_tokens,
            temperature=temperature,
            overall_deadline=overall_deadline
        )

    async def call(
        self,
        model: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        max_tokens: int = 2500,
        temperature: float = 0.4,
        provider: str = "",
        *,
        stage_tag: Optional[str] = None,
        overall_deadline: float = 75.0
    ) -> str:
        """Convenience alias for call_model."""
        return await self.call_model(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            provider=provider,
            stage_tag=stage_tag,
            overall_deadline=overall_deadline
        )

    def extract_json(self, text: str, default_schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Robustly extracts and repairs JSON from an LLM response string."""
        import json_repair

        if not text or not text.strip():
            print("[JSON Parser] Warning: Received empty response from model. Using default schema.")
            fallback = default_schema.copy() if default_schema else {}
            fallback["_parse_error"] = True
            return fallback

        cleaned = text.strip()

        # 1. Try explicit ```json ... ``` code block first
        match_json = re.search(r"```json\s*([\s\S]*?)\s*```", cleaned, flags=re.IGNORECASE)
        if match_json:
            candidate = match_json.group(1).strip()
        else:
            # Strip non-JSON ```python ... ``` blocks so braces inside Python dicts aren't mistaken for root JSON
            without_py = re.sub(r"```python[\s\S]*?```", "", cleaned, flags=re.IGNORECASE).strip()
            match_generic = re.search(r"```\s*(\{[\s\S]*?\})\s*```", without_py)
            candidate = match_generic.group(1).strip() if match_generic else without_py

        # 2. Try substring from first '{' to last '}'
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = candidate[start:end+1]

        # 3. Parse with json_repair
        try:
            parsed = json_repair.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
            elif isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                return {"items": parsed}
        except Exception:
            pass

        # 4. Fallback to standard json loads
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception as e:
            print(f"[JSON Parser] Notice: standard json parse failed ({e}). Constructing structured fallback...")

        # 5. Guaranteed fallback with explicit parse error flag
        fallback = default_schema.copy() if default_schema else {}
        fallback["raw_text"] = text
        fallback["parse_status"] = "extracted_raw"
        fallback["_parse_error"] = True
        return fallback


# Global client instance
model_caller = ModelCaller()
