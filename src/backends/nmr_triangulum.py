# src/backends/nmr_triangulum.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class TriangulumConfig:
    ip: str
    port: int
    account: str
    password: str
    task_name: str = "qae_mlae"
    task_desc: str = "MLAE-style QAE experiment"
    optimization_level: int = 0


class TriangulumBackend:
    """
    Thin wrapper around the SpinQit NMR backend for Triangulum.

    This wrapper tries several common SpinQit execution patterns:
      1) compile + NMRConfig + execute(compiled, config)
      2) compile + NMRConfig + execute(compiled, config, shots=...)
      3) execute(circuit, config)
      4) execute(circuit, config, shots=...)
      5) run(circuit, config, shots=...)

    The goal is to isolate version-specific API differences in a single place.
    """

    def __init__(self, cfg: TriangulumConfig):
        self.cfg = cfg
        self._compiler, self._engine, self._nmr_cfg_cls = self._make_runtime()

    @staticmethod
    def _make_runtime():
        try:
            from spinqit import get_nmr, NMRConfig, get_compiler  # type: ignore
        except Exception as e:
            raise ImportError(
                "Could not import get_nmr, NMRConfig, or get_compiler from spinqit. "
                "Please adapt TriangulumBackend to your local SpinQit version."
            ) from e

        compiler = get_compiler("native")
        engine = get_nmr()
        return compiler, engine, NMRConfig

    def _build_config(self, shots: int):
        conf = self._nmr_cfg_cls()
        conf.configure_ip(self.cfg.ip)
        conf.configure_port(int(self.cfg.port))
        conf.configure_account(self.cfg.account, self.cfg.password)
        conf.configure_task(self.cfg.task_name, self.cfg.task_desc)

        # Some builds may expose shot configuration in the backend config.
        try:
            conf.configure_shots(int(shots))
        except Exception:
            pass

        return conf

    @staticmethod
    def _extract_counts(result) -> Dict[str, int]:
        if isinstance(result, dict):
            return result
        if hasattr(result, "counts"):
            return result.counts
        if hasattr(result, "get_counts"):
            return result.get_counts()

        raise RuntimeError(
            "NMR backend returned an unsupported result type; "
            "please adapt counts extraction."
        )

    def run(self, circuit, shots: int = 4096) -> Dict[str, int]:
        compiler = self._compiler
        engine = self._engine
        conf = self._build_config(shots)

        errors = []

        compiled = None
        try:
            compiled = compiler.compile(circuit, self.cfg.optimization_level)
        except Exception as e:
            errors.append(f"compile(circuit, optimization_level) failed: {e!r}")

        candidates = []

        if compiled is not None:
            candidates.extend(
                [
                    ("engine.execute(compiled, conf)", lambda: engine.execute(compiled, conf)),
                    ("engine.execute(compiled, conf, shots=shots)", lambda: engine.execute(compiled, conf, shots=int(shots))),
                    ("engine.run(compiled, conf)", lambda: engine.run(compiled, conf)),
                    ("engine.run(compiled, conf, shots=shots)", lambda: engine.run(compiled, conf, shots=int(shots))),
                ]
            )

        candidates.extend(
            [
                ("engine.execute(circuit, conf)", lambda: engine.execute(circuit, conf)),
                ("engine.execute(circuit, conf, shots=shots)", lambda: engine.execute(circuit, conf, shots=int(shots))),
                ("engine.run(circuit, conf)", lambda: engine.run(circuit, conf)),
                ("engine.run(circuit, conf, shots=shots)", lambda: engine.run(circuit, conf, shots=int(shots))),
            ]
        )

        for label, fn in candidates:
            try:
                result = fn()
                return self._extract_counts(result)
            except Exception as e:
                errors.append(f"{label} failed: {e!r}")

        raise RuntimeError(
            "Could not execute circuit on NMR backend. Tried multiple SpinQit call patterns.\n"
            + "\n".join(errors)
        )