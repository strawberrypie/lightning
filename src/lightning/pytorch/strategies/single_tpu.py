# Copyright The Lightning AI team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import os
from typing import Dict, Optional

import torch

import lightning.pytorch as pl
from lightning.fabric.accelerators.tpu import _XLA_AVAILABLE
from lightning.fabric.plugins import CheckpointIO, XLACheckpointIO
from lightning.fabric.utilities.types import _DEVICE
from lightning.pytorch.plugins.io.wrapper import _WrappingCheckpointIO
from lightning.pytorch.plugins.precision import PrecisionPlugin
from lightning.pytorch.strategies.single_device import SingleDeviceStrategy
from lightning.pytorch.utilities import find_shared_parameters, set_shared_parameters


class SingleTPUStrategy(SingleDeviceStrategy):
    """Strategy for training on a single TPU device."""

    strategy_name = "single_tpu"

    def __init__(
        self,
        device: _DEVICE,
        accelerator: Optional["pl.accelerators.Accelerator"] = None,
        checkpoint_io: Optional[CheckpointIO] = None,
        precision_plugin: Optional[PrecisionPlugin] = None,
        debug: bool = False,
    ):
        if not _XLA_AVAILABLE:
            raise ModuleNotFoundError(str(_XLA_AVAILABLE))
        if isinstance(device, torch.device):
            # unwrap the `torch.device` in favor of `xla_device`
            device = device.index
        import torch_xla.core.xla_model as xm

        super().__init__(
            accelerator=accelerator,
            device=xm.xla_device(device),
            checkpoint_io=checkpoint_io,
            precision_plugin=precision_plugin,
        )
        self.debug = debug

    @property
    def checkpoint_io(self) -> CheckpointIO:
        if self._checkpoint_io is None:
            self._checkpoint_io = XLACheckpointIO()
        elif isinstance(self._checkpoint_io, _WrappingCheckpointIO):
            self._checkpoint_io.checkpoint_io = XLACheckpointIO()

        return self._checkpoint_io

    @checkpoint_io.setter
    def checkpoint_io(self, io: Optional[CheckpointIO]) -> None:
        self._checkpoint_io = io

    def setup(self, trainer: "pl.Trainer") -> None:
        assert self.model, "self.model must be set before find_shared_parameters(self.model)"
        shared_params = find_shared_parameters(self.model)
        self.model_to_device()
        set_shared_parameters(self.model, shared_params)
        super().setup(trainer)

        if self.debug:
            os.environ["PT_XLA_DEBUG"] = str(1)

    @classmethod
    def register_strategies(cls, strategy_registry: Dict) -> None:
        strategy_registry.register(
            cls.strategy_name,
            cls,
            description=f"{cls.__class__.__name__}",
        )

    def teardown(self) -> None:
        super().teardown()
        os.environ.pop("PT_XLA_DEBUG", None)
