"""Central constants. Model ids are read, never built."""
import os

LLM_PROVIDER = os.getenv("CRISIS_OS_LLM_PROVIDER", "local").lower()
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
MODEL_DEFAULT = os.getenv("CRISIS_OS_MODEL_DEFAULT", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
MODEL_HEAVY = os.getenv("CRISIS_OS_MODEL_HEAVY", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
PORT = int(os.getenv("CRISIS_OS_PORT", "8081"))
