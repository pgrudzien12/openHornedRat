# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false
"""The codec for :class:`~whshr.glue_runtime.GlueRuntimeState`: which classes a saved interpreter may contain."""

from typing import Any

from .glue import MissionRef
from .glue_animation import GlueBitmapAnimator
from .glue_runtime import (ContextSnapshot, GlueRuntimeState, PendingRequest, RuntimeAnimation, ScriptFrame,
                           WindowInstance)
from .portraits import PortraitAnimator
from .state_codec import Codec

# The instruction trace is a debugging aid that grows without bound; it is not part of a save.
CODEC = Codec([GlueRuntimeState, ScriptFrame, WindowInstance, PendingRequest, RuntimeAnimation, ContextSnapshot,
               MissionRef, GlueBitmapAnimator, PortraitAnimator],
              skip={GlueRuntimeState: frozenset({"trace"})})


def encode_state(state: GlueRuntimeState) -> Any:
    return CODEC.encode(state)


def decode_state(data: Any) -> GlueRuntimeState:
    state = CODEC.decode(data)
    if not isinstance(state, GlueRuntimeState):
        raise ValueError("the saved interpreter state is not a GlueRuntimeState")
    # A save carries no sound: a speech line that was being read out is not resumed mid-word.
    state.speech_lines, state.speech_active, state.speech_overlays = (), False, {}
    return state
