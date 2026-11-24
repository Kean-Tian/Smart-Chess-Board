"""Noninteractive UI adapter for the existing OpenRouter coaching transport."""
import os

from api_key_store import load_api_key
from openrouter_engine import OpenRouter, OpenRouterError, ask_coaching_hint


def request_ui_coaching(fen, legal):
    # 只在已选择 coaching 的回合读取本机 Key，不在 GUI 后台弹出终端输入。
    key = os.environ.get("OPENROUTER_API_KEY", "").strip() or load_api_key()
    if not key:
        raise OpenRouterError("No AI coaching key is saved on this Pi. Set it up, then retry.", retryable=False)
    provider = OpenRouter(key, timeout=8, attempts=1, report=lambda *_: None)
    # 向工作线程传局面和合法走法的快照，不共享可变的棋规对象。
    return ask_coaching_hint(fen, legal, provider.api_key, provider.model, provider.timeout)
