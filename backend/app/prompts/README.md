# System Prompt Assets

This directory is the runtime SSOT for versioned system prompts loaded through `PromptCatalog`.

## Language policy

- `*_system.md` is the English runtime prompt used by the application.
- `*_system_KOR.md` is the read-only Korean source archive for human review and traceability.
- Application code must reference only `*_system.md`; `_KOR.md` files are never selected as runtime prompts.
- User-facing JSON values may still be requested in Korean because the Console audience is Korean. Instructions, decision procedures, evidence rules, and model guidance remain English.

## Model compatibility policy

Runtime prompts use one provider-neutral contract instead of duplicating business rules per vendor:

- Smaller/local models receive a fixed deterministic procedure, exact identifier-copy rules, schema-first output, and JSON-only constraints.
- Reasoning-capable models may reconcile evidence privately but must not expose chain-of-thought.
- Vision-capable models receive an ordered observation procedure before schema emission.
- Model selection remains the responsibility of Core `ModelRegistry`/`ModelSelector`; prompt files do not hardcode provider or model IDs.

## Change rules

1. Preserve schema keys, enums, placeholders, evidence-reference formats, and prompt version metadata unless the corresponding contract is migrated.
2. Never add secret values, production credentials, or personal data to prompts or examples.
3. Keep the Korean archive unchanged when only optimizing the English runtime prompt. If the Korean source contract itself changes, update both files intentionally and document the migration.
4. Run prompt guidance and Core prompt-loader tests before commit.
