from __future__ import annotations

from typing import Literal

from src.direction_scorer import score_direction
from src.llm_client import LLMClient
from src.memory import InterviewMemory, TurnEvaluation


FlowAction = Literal["follow_up", "next_direction"]


class InterviewFlowController:
    """Decides interview flow transitions from evaluation + memory state.

    InterviewMemory stores state and evidence. This controller owns the policy
    for whether the next turn should continue the same plan direction or move
    to the next direction/stage.
    """

    def decide_next_action(self, memory: InterviewMemory) -> FlowAction:
        evaluation = memory.latest_evaluation
        if evaluation is None:
            return "next_direction"
        if self._should_move_on(memory, evaluation):
            return "next_direction"
        if evaluation.need_follow_up:
            return "follow_up"
        return "next_direction"

    def apply(
        self,
        memory: InterviewMemory,
        *,
        llm: LLMClient,
        plan: dict,
        jd: dict,
        resume: dict,
    ) -> tuple[FlowAction, dict | None]:
        action = self.decide_next_action(memory)
        score = None
        if action == "follow_up":
            memory.continue_current_direction()
        else:
            score = self._score_current_direction(memory, llm=llm, plan=plan, jd=jd, resume=resume)
            memory.advance_to_next_direction()
        return action, score

    def _should_move_on(self, memory: InterviewMemory, evaluation: TurnEvaluation) -> bool:
        return (
            evaluation.direction_complete
            or evaluation.signal_sufficient
            or evaluation.candidate_admitted_gap
            or evaluation.new_information_gain == "low"
            or memory.followup_limit_reached()
            or memory.current_stage_limit_reached()
        )

    def _score_current_direction(
        self,
        memory: InterviewMemory,
        *,
        llm: LLMClient,
        plan: dict,
        jd: dict,
        resume: dict,
    ) -> dict | None:
        turns = memory.current_direction_turns
        if not turns:
            return None
        latest = turns[-1]
        score = score_direction(
            llm,
            direction=latest.focus_area,
            stage=latest.stage_name,
            turns=turns,
            plan=plan,
            jd=jd,
            resume=resume,
        )
        memory.add_direction_score(score)
        return score
