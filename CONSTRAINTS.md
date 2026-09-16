# Inscrona — Hard Constraints (read before every task, no exceptions)

- Backend: FastAPI only. NEVER Fastify, NestJS, Express.
- Model serving: Ollama only. NEVER Docker, NEVER vLLM, NEVER LM Studio for production paths.
- Models: glm-ocr + llama3.2:3b via Ollama. NEVER swap or add a third model without flagging in PROGRESS.md and stopping for approval.
- Storage: local filesystem only (./uploads, ./results as JSON). NEVER Postgres, Prisma, MinIO, Redis, BullMQ.
- HEIC→JPEG conversion: already implemented — do not rebuild it, locate and reuse it.
- Every task must end in one of two states in PROGRESS.md: DONE (with actual command output as proof) or BLOCKED (with the exact error).
- No task is DONE without being run once and showing real output. A code diff with no execution log is not DONE.
- If a task requires installing a new framework, service, or dependency not listed above, STOP. Write it as BLOCKED with the reason. Do not install it.
