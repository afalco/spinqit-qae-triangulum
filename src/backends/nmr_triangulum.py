# src/backends/nmr_triangulum.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class TriangulumConfig:
    ip: str
    port: int
    account: str
    password: str
    task_name: str = "qae_mlae"
    task_desc: str = "MLAE-style QAE experiment"


class TriangulumBackend:
    """
    Thin wrapper around SpinQit NMR backend.

    IMPORTANT:
    SpinQit backend execution API can differ across versions. This wrapper isolates
    those differences: adapt the `run()` method to your installed SpinQit version.
    """

    def __init__(self, cfg: TriangulumConfig):
        self.cfg = cfg
        self._engine, self._engine_cfg = self._make_engine_and_config(cfg)

    @staticmethod
    def _make_engine_and_config(cfg: TriangulumConfig):
        from spinqit import get_nmr, NMRConfig  # type: ignore

        engine = get_nmr()
        conf = NMRConfig()
        conf.configure_ip(cfg.ip)
        conf.configure_port(int(cfg.port))
        conf.configure_account(cfg.account, cfg.password)
        conf.configure_task(cfg.task_name, cfg.task_desc)
        return engine, conf

    def run(self, circuit, shots: int = 4096) -> Dict[str, int]:
        """
        Execute a circuit on Triangulum and return counts as {bitstring: count}.

        You may need to adapt one of these lines depending on your SpinQit version:
          - engine.execute(circuit, config, shots=shots)
          - engine.run(circuit, config, shots=shots)
          - engine.submit(...)
        """
        engine = self._engine
        conf = self._engine_cfg

        # Try common invocation patterns
        result = None
        try:
            result = engine.execute(circuit, conf, shots=shots)
        except Exception:
            try:
                result = engine.run(circuit, conf, shots=shots)
            except Exception as e:
                raise RuntimeError(
                    "Could not execute circuit on NMR backend. "
                    "Please adapt TriangulumBackend.run() to your SpinQit version."
                ) from e

        # Extract counts
        if isinstance(result, dict):
            return result
        if hasattr(result, "counts"):
            return result.counts
        if hasattr(result, "get_counts"):
            return result.get_counts()

        raise RuntimeError("NMR backend returned an unsupported result type; please adapt counts extraction.")
