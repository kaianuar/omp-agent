# Finalized Model Configuration (all tests run-the-code validated, 2026-08-15)

## Provider status

| Provider | Status | Notes |
|---|---|---|
| Xiaomi MiMo | ✅ working | builder + plan; key in ~/.hermes/.env |
| OpenRouter | ✅ working (key set) | critic + all fallbacks; key in ~/.hermes/.env |
| OpenCode Go | ⚠️ throttles (403 under load) | avoid as hot-path critic |
| DeepSeek dedicated | ⚠️ price rose | use OpenRouter instead |
| ollama-cloud | ❌ EXPIRED | removed |

## Primary roles (validated, run-the-code)

| Role | Model | Provider | In/M | Status |
|---|---|---|---|---|
| builder (default) | xiaomi-token-plan-sgp/mimo-v2.5-pro | Xiaomi MiMo | sub | ✅ PASS |
| plan | xiaomi-token-plan-sgp/mimo-v2.5 | Xiaomi MiMo | | ✅ PASS |
| critic (Gate 2) | z-ai/glm-5.2 | OpenRouter | $0.49 | ✅ PASS |

## Fallback matrix (ALL dedupe-probe tested 2026-08-15)

### Critic fallbacks (distinct from MiMo builder)
| Rank | Model | In/M | Result |
|---|---|---|---|
| 1 | qwen/qwen3-coder-30b-a3b-instruct | $0.070 | ✅ PASS — cheapest strong |
| 2 | minimax/minimax-m3 | $0.300 | ✅ PASS — cheapest of kimi/minimax tier, input-cheap ≥ good for review |
| 3 | moonshotai/kimi-k2.7-code | $0.710 | ✅ PASS — code-tuned, pricier |
| ✗ | moonshotai/kimi-k2.6 | $0.650 | ❌ FAIL — empty output on OpenRouter, DO NOT use |
| — | deepseek/deepseek-v4-flash | $0.077 | (validated in AlexQu pool; not re-run here) |

### Builder fallbacks
| Rank | Model | In/M | Result |
|---|---|---|---|
| 1 | qwen/qwen3-coder-30b-a3b-instruct | $0.070 | ✅ PASS |
| 2 | deepseek/deepseek-v4-flash | $0.077 | validated |

### Free fallbacks (rate-limited, light use only)
qwen/qwen3-coder-30b-a3b-instruct:free, deepseek/deepseek-v4-flash:free,
z-ai/glm-4.7-flash:free, openai/gpt-oss-120b:free

## Critical implementation rules (VALIDATED)
1. **Reasoning models return EMPTY if max_tokens too low** → always max_tokens >= 4000.
   (glm-5.2, mimo, kimi all reasoning; @700 empty, @4000 fine.)
2. **Builder MUST differ from critic** (cross-model adversarial review). Don't set equal.
3. **kimi-k2.6 is NOT usable on OpenRouter** (empty output) despite being in the local pool.
4. **OpenCode Go throttles** — avoid as hot-path critic.

## How to switch
- Critic: CRITIC_MODEL env or tests/review_gate.sh default.
- Builder: modelRoles in .omp/config.yml.
- Re-validate monthly / when subs or prices change.
