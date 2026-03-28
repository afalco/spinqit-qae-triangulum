from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from .bit_order import ReportedOrder, canonicalize_counts


@dataclass
class SimulatorConfig:
    shots: int = 4096
    optimization_level: int = 0
    reported_order: ReportedOrder = "q0q1q2"


class SimulatorBackend:
    """
    Thin wrapper around the SpinQit basic simulator backend.

    All returned counts are canonicalized to the repository-wide state order:
        q0q1q2  ->  ['000', '001', ..., '111']

    This means downstream code does not need to guess bit order ad hoc.
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

    @staticmethod
    def _extract_counts(result) -> Dict[str, int]:
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

        raw_counts = self._extract_counts(result)
        return canonicalize_counts(raw_counts, reported_order=self.cfg.reported_order, nbits=3)
