#!/usr/bin/env python3
"""
codex_lm.py - DSPy LM adapter for OpenAI Codex CLI

Wraps `codex exec` as a DSPy language model provider so DSPy Signatures
can use Codex subscriptions without API keys at runtime.

Usage:
    import dspy
    from codex_lm import CodexLM

    lm = CodexLM()
    dspy.configure(lm=lm)
"""
import subprocess
import time
from typing import Any

from call_codex import build_codex_command, verify_codex_cli

try:
    from dspy.clients.base_lm import BaseLM
except ImportError:
    raise ImportError("DSPy is required: uv pip install dspy>=2.6.0")


class CodexLM(BaseLM):
    """DSPy LM adapter that routes inference through `codex exec` subprocess."""

    def __init__(self, timeout: int = 600, **kwargs):
        super().__init__(model="codex/exec", model_type="chat", **kwargs)
        self.timeout = timeout

        # Verify CLI availability at init time
        cli_info = verify_codex_cli()
        if cli_info["error"]:
            raise RuntimeError(f"Codex CLI not available: {cli_info['error']}")
        self.cli_version = cli_info["version"]
        self.supports_skip_git = cli_info["supports_skip_git"]

    def _messages_to_prompt(self, messages: list[dict[str, Any]]) -> str:
        """Flatten DSPy chat messages into a single prompt string for codex exec.

        DSPy sends messages as [{"role": "system", ...}, {"role": "user", ...}].
        Codex exec reads a single prompt from stdin, so we concatenate them.
        """
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                parts.append(content)
            elif role == "user":
                parts.append(content)
            elif role == "assistant":
                # Include prior assistant turns for context
                parts.append(f"[Previous response]\n{content}")
        return "\n\n".join(parts)

    def forward(
        self,
        prompt: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> list[dict[str, Any]]:
        """Execute a single LM call through codex exec.

        Returns OpenAI-compatible response format that DSPy expects.
        """
        # Build the text prompt from either raw prompt or messages
        if messages:
            text_prompt = self._messages_to_prompt(messages)
        elif prompt:
            text_prompt = prompt
        else:
            raise ValueError("Either prompt or messages must be provided")

        # Build command using shared function
        cmd = build_codex_command(self.supports_skip_git)

        # Call codex exec via subprocess
        start = time.time()
        try:
            result = subprocess.run(
                cmd,
                input=text_prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Codex exec timed out after {self.timeout}s")
        except FileNotFoundError:
            raise RuntimeError("codex command not found")

        duration = time.time() - start

        if result.returncode != 0:
            raise RuntimeError(
                f"Codex exec failed (code {result.returncode}): {result.stderr}"
            )

        output_text = result.stdout.strip()

        # Return OpenAI chat-completion-compatible format
        response = {
            "id": f"codex-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "codex/exec",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": output_text,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": len(text_prompt.split()),
                "completion_tokens": len(output_text.split()),
                "total_tokens": len(text_prompt.split()) + len(output_text.split()),
            },
        }

        # Log the call for DSPy history
        self.history.append(
            {
                "prompt": prompt,
                "messages": messages,
                "kwargs": kwargs,
                "response": response,
                "outputs": [output_text],
                "usage": response["usage"],
                "cost": 0.0,
                "timestamp": time.time(),
                "duration": duration,
            }
        )

        return [output_text]

    async def aforward(
        self,
        prompt: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> list[dict[str, Any]]:
        """Async variant - delegates to sync forward since codex exec is subprocess-based."""
        return self.forward(prompt=prompt, messages=messages, **kwargs)


if __name__ == "__main__":
    lm = CodexLM()
    print(f"CodexLM initialized: {lm.cli_version}")
    print(f"Supports --skip-git-repo-check: {lm.supports_skip_git}")
