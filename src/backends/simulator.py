from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class SimulatorConfig:
    shots: int = 4096
    optimization_level: int = 0


class SimulatorBackend:
    """
    Thin wrapper around the SpinQit basic simulator backend.

    SpinQit 0.2.2 uses the following flow:
      1) get compiler + backend
      2) compile the circuit
      3) configure shots via BasicSimulatorConfig
      4) execute(compiled_circuit, config)

    The official docs example uses:
        comp = get_compiler("native")
        engine = get_basic_simulator()
        exe = comp.compile(circ, optimization_level)
        config = BasicSimulatorConfig()
        config.configure_shots(1024)
        result = engine.execute(exe, config)
        print(result.counts)
     [oai_citation:1‡doc.spinq.cn](https://doc.spinq.cn/doc/spinqit/basics/basics.html?utm_source=chatgpt.com)
    """

    def __init__(self, cfg: SimulatorConfig = SimulatorConfig()):
        self.cfg = cfg
        self._compiler, self._engine, self._simcfg_cls = self._make_runtime()

    @staticmethod
    def _make_runtime():
        try:
            from spinqit import get_basic_simulator, get_compiler, BasicSimulatorConfig  # type: ignore
        except Exception as e:
            raise ImportError(
                "Could not import get_basic_simulator, get_compiler, or BasicSimulatorConfig "
                "from spinqit. Please adapt SimulatorBackend to your local SpinQit version."
            ) from e

        compiler = get_compiler("native")
        engine = get_basic_simulator()
        return compiler, engine, BasicSimulatorConfig

    def run(self, circuit, shots: int = 4096) -> Dict[str, int]:
        compiler = self._compiler
        engine = self._engine
        BasicSimulatorConfig = self._simcfg_cls

        try:
            exe = compiler.compile(circuit, self.cfg.optimization_level)

            config = BasicSimulatorConfig()
            config.configure_shots(int(shots))

            result = engine.execute(exe, config)
        except Exception as e:
            raise RuntimeError(
                "Could not execute circuit on simulator backend using the "
                "SpinQit compile + BasicSimulatorConfig flow."
            ) from e

        if isinstance(result, dict):
            return result
        if hasattr(result, "counts"):
            return result.counts
        if hasattr(result, "get_counts"):
            return result.get_counts()

        raise RuntimeError(
            "Simulator backend returned an unsupported result type; "
            "please adapt counts extraction."
        )